"""Cliente OIDC da Lucy (authorization code + PKCE).

A Lucy é o provedor de identidade; o jogo continua emitindo o próprio JWT no
cookie ``auth_token``. Assim, decorators, sockets e saves não precisam saber
de OIDC: depois do callback a conta local é provisionada e o login segue igual.
"""
import base64
import hashlib
import json
import re
import secrets
import threading
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import jwt
from jwt.algorithms import RSAAlgorithm

from twilight import config
from twilight.auth.service import hash_password, update_account, upsert_account
from twilight.config import now_sp_iso
from twilight.offload import run_offloop
from twilight.storage.db import account_exists, find_linked_account, get_account as get_account_record


class OidcError(Exception):
    """Falha de configuração, rede ou validação do token da Lucy."""


_CACHE_TTL = 3600
_DISCOVERY = {'at': 0.0, 'doc': None}
_JWKS = {'at': 0.0, 'keys': []}
_LOCK = threading.Lock()


def _http_json(url, *, data=None, headers=None):
    """GET/POST form-urlencoded via stdlib, sem dependência de requests."""
    request_headers = dict(headers or {})
    body = None
    if data is not None:
        body = urlencode(data).encode('utf-8')
        request_headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
    req = Request(
        url,
        data=body,
        headers=request_headers,
        method='POST' if body is not None else 'GET',
    )
    try:
        # IO síncrono fora do hub gevent (o worker é único).
        response = run_offloop(urlopen, req, timeout=config.LUCY_TIMEOUT_SECONDS)
        with response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace')[:400]
        raise OidcError(f'HTTP {exc.code} em {urlparse(url).path}: {detail}') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise OidcError(f'Não foi possível contatar {urlparse(url).netloc}: {exc}') from exc

    try:
        return json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OidcError(f'Resposta inválida de {urlparse(url).path}') from exc


def is_configured() -> bool:
    """Falta alguma variável obrigatória do cliente?"""
    return bool(
        config.LUCY_ISSUER
        and config.LUCY_CLIENT_ID
        and config.LUCY_CLIENT_SECRET
        and config.LUCY_REDIRECT_URI
    )


def discovery() -> dict:
    """Documento OIDC da Lucy, com cache curto em memória do processo."""
    with _LOCK:
        cached = _DISCOVERY['doc']
        if cached and time.time() - _DISCOVERY['at'] < _CACHE_TTL:
            return cached

    doc = _http_json(config.LUCY_DISCOVERY_URL)
    issuer = str(doc.get('issuer') or '').rstrip('/')
    expected = config.LUCY_ISSUER.rstrip('/')
    if issuer != expected:
        raise OidcError(f'issuer da descoberta ({issuer}) não confere com LUCY_ISSUER ({expected})')
    for field in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
        if not doc.get(field):
            raise OidcError(f'Descoberta da Lucy sem {field}')

    with _LOCK:
        _DISCOVERY['doc'] = doc
        _DISCOVERY['at'] = time.time()
    return doc


def jwks() -> list:
    """Chaves públicas RSA da Lucy, com cache curto."""
    with _LOCK:
        cached = _JWKS['keys']
        if cached and time.time() - _JWKS['at'] < _CACHE_TTL:
            return cached

    doc = discovery()
    payload = _http_json(doc['jwks_uri'])
    keys = [key for key in (payload.get('keys') or []) if key.get('kty') == 'RSA']
    if not keys:
        raise OidcError('JWKS da Lucy não trouxe chaves RSA')

    with _LOCK:
        _JWKS['keys'] = keys
        _JWKS['at'] = time.time()
    return keys


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def authorization_url(state: str, challenge: str) -> str:
    doc = discovery()
    params = {
        'client_id': config.LUCY_CLIENT_ID,
        'redirect_uri': config.LUCY_REDIRECT_URI,
        'response_type': 'code',
        'scope': config.LUCY_SCOPES,
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    return f"{doc['authorization_endpoint']}?{urlencode(params)}"


def exchange_code(code: str, verifier: str) -> dict:
    doc = discovery()
    tokens = _http_json(doc['token_endpoint'], data={
        'grant_type': 'authorization_code',
        'client_id': config.LUCY_CLIENT_ID,
        'client_secret': config.LUCY_CLIENT_SECRET,
        'code': code,
        'redirect_uri': config.LUCY_REDIRECT_URI,
        'code_verifier': verifier,
    })
    if tokens.get('error'):
        raise OidcError(f"Lucy recusou o código: {tokens['error']}")
    if not tokens.get('id_token'):
        raise OidcError('Lucy não devolveu id_token')
    return tokens


def verify_id_token(id_token: str) -> dict:
    """Valida assinatura RS256, issuer, audiência, expiração e sub."""
    header = jwt.get_unverified_header(id_token)
    if header.get('alg') != 'RS256':
        raise OidcError(f'Algoritmo inesperado no id_token: {header.get("alg")}')

    kid = header.get('kid')
    keys = jwks()
    key_data = next((item for item in keys if item.get('kid') == kid), None)
    if key_data is None and len(keys) == 1:
        key_data = keys[0]
    if key_data is None:
        raise OidcError(f'Chave {kid or "(sem kid)"} não está no JWKS da Lucy')

    try:
        public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
        return jwt.decode(
            id_token,
            key=public_key,
            algorithms=['RS256'],
            audience=config.LUCY_CLIENT_ID,
            issuer=config.LUCY_ISSUER,
            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
        )
    except jwt.PyJWTError as exc:
        raise OidcError(f'id_token inválido: {exc}') from exc


def fetch_claims(tokens: dict) -> dict:
    """Claims do id_token, completados com /sso/userinfo quando preciso."""
    claims = verify_id_token(tokens['id_token'])
    if not claims.get('email') or not claims.get('name'):
        doc = discovery()
        endpoint = doc.get('userinfo_endpoint')
        if endpoint and tokens.get('access_token'):
            try:
                info = _http_json(endpoint, headers={
                    'Authorization': f"Bearer {tokens['access_token']}",
                })
            except OidcError:
                info = {}
            for field in ('name', 'preferred_username', 'email', 'email_verified', 'picture'):
                if not claims.get(field) and field in info:
                    claims[field] = info[field]
    return claims


def safe_next(value) -> str:
    """Só aceita caminho relativo local (nada de redirect externo)."""
    if not isinstance(value, str) or not value:
        return '/'
    if not value.startswith('/') or value.startswith('//'):
        return '/'
    if any(char in value for char in ('\\', '\r', '\n')):
        return '/'
    return value[:300]


def normalize_username(raw) -> str:
    """Converte o sub/preferred_username da Lucy no usuário do jogo."""
    value = unicodedata.normalize('NFKD', str(raw or '')).encode('ascii', 'ignore').decode('utf-8')
    value = re.sub(r'[^a-z0-9_]+', '_', value.lower()).strip('_')
    value = re.sub(r'_+', '_', value) or 'lucy'
    return value[:20].ljust(3, '_')


def provision(claims: dict) -> str:
    """Encontra/cria a conta local do jogador e devolve o username dela."""
    sub = str(claims.get('sub') or '').strip()
    if not sub:
        raise OidcError('id_token da Lucy sem sub')

    issuer = config.LUCY_ISSUER.rstrip('/')
    linked = find_linked_account(sub, issuer)
    username = linked[0] if linked else None
    display_name = str(claims.get('name') or claims.get('preferred_username') or sub)[:120]
    email = str(claims.get('email') or '')[:200]
    link_fields = {
        'auth_provider': 'lucy',
        'oidc_sub': sub,
        'oidc_issuer': issuer,
        'oidc_email': email,
        'realname': display_name,
    }

    if username:
        update_account(username, link_fields)
        return username

    candidate = normalize_username(claims.get('preferred_username') or sub)
    existing = get_account_record(candidate)
    if existing:
        if config.LUCY_LINK_BY_USERNAME and not existing.get('oidc_sub'):
            # Conta interna antiga: preserva progresso, saves e admin_level.
            update_account(candidate, link_fields)
            return candidate
        suffix = hashlib.sha256(f'{issuer}|{sub}'.encode('utf-8')).hexdigest()[:6]
        candidate = f'{candidate[:13]}_{suffix}'
        while account_exists(candidate):
            suffix = hashlib.sha256(suffix.encode('utf-8')).hexdigest()[:6]
            candidate = f'{candidate[:13]}_{suffix}'

    if not config.LUCY_ALLOW_SIGNUP:
        raise OidcError('Seu usuário da Lucy ainda não tem conta neste jogo')

    upsert_account(candidate, {
        'password': hash_password(secrets.token_urlsafe(32)),  # inutilizável
        'created_at': now_sp_iso(),
        'current_game': None,
        **link_fields,
    })
    return candidate
