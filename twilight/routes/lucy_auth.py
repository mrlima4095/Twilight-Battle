"""Rotas do login OIDC com a Lucy."""
import logging
import secrets
import time
from urllib.parse import quote

from flask import Blueprint, jsonify, redirect, request, session

from twilight import config
from twilight.auth import lucy as lucy_oidc
from twilight.auth.service import create_token

logger = logging.getLogger(__name__)

bp = Blueprint('lucy_auth', __name__)

_STATE_TTL_SECONDS = 600  # 10 min para o usuário aprovar na Lucy


def _set_auth_cookie(response, token):
    response.set_cookie(
        'auth_token',
        token,
        httponly=True,
        secure=config.SECURE_COOKIES,
        samesite='Lax',
        max_age=config.JWT_EXPIRATION_HOURS * 3600,
    )
    return response


def _login_error(reason: str):
    """Volta ao formulário com um código curto (detalhe fica no log)."""
    return redirect(f'/login?error={quote(reason[:40])}')


@bp.route('/auth/lucy/login')
def lucy_login():
    """Inicia o fluxo: guarda state/PKCE no cookie de sessão e vai à Lucy."""
    if not config.auth_allows_lucy():
        return redirect('/login')
    if not lucy_oidc.is_configured():
        return jsonify({
            'success': False,
            'message': 'Login da Lucy não configurado nesta instância (LUCY_CLIENT_ID/SECRET/REDIRECT_URI).',
        }), 503

    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    challenge = lucy_oidc.pkce_challenge(verifier)
    session['lucy_oidc'] = {
        'state': state,
        'verifier': verifier,
        'next': lucy_oidc.safe_next(request.args.get('next')),
        'ts': time.time(),
    }
    try:
        target = lucy_oidc.authorization_url(state, challenge)
    except lucy_oidc.OidcError as exc:
        logger.error('[lucy-oidc] falha ao montar authorize: %s', exc)
        return _login_error('discovery_failed')
    return redirect(target)


@bp.route('/auth/lucy/callback')
def lucy_callback():
    """Troca o código, valida o id_token, cria a conta e emite o JWT do jogo."""
    pending = session.pop('lucy_oidc', None)

    provider_error = (request.args.get('error') or '').strip()
    if provider_error:
        logger.warning('[lucy-oidc] provedor retornou erro: %s', provider_error[:200])
        return _login_error('provider_error')

    if not pending or time.time() - float(pending.get('ts') or 0) > _STATE_TTL_SECONDS:
        return _login_error('expired')
    if not secrets.compare_digest((request.args.get('state') or ''), str(pending.get('state') or '')):
        logger.warning('[lucy-oidc] state não confere')
        return _login_error('invalid_state')

    code = (request.args.get('code') or '').strip()
    if not code:
        return _login_error('missing_code')

    try:
        tokens = lucy_oidc.exchange_code(code, str(pending.get('verifier') or ''))
        claims = lucy_oidc.fetch_claims(tokens)
        username = lucy_oidc.provision(claims)
    except lucy_oidc.OidcError as exc:
        logger.error('[lucy-oidc] falha no callback: %s', exc)
        return _login_error('login_failed')
    except Exception:
        logger.exception('[lucy-oidc] erro inesperado no callback')
        return _login_error('login_failed')

    target = lucy_oidc.safe_next(pending.get('next'))
    return _set_auth_cookie(redirect(target), create_token(username))
