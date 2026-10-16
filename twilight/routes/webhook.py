"""Webhooks externos (Forgejo/GitHub).

Desativado por padrão. Para habilitar, defina a variável de ambiente
WEBHOOK_SECRET com um valor forte e configure o provedor para enviar a
assinatura HMAC-SHA256 (header X-Hub-Signature-256). Sem o segredo, o
endpoint responde 404 — nunca aceitamos um push anônimo que dispare
`git pull` + restart do processo.
"""
import hashlib
import hmac
import os
import subprocess
import sys
import threading
import time

from flask import Blueprint, jsonify, request

bp = Blueprint('webhook', __name__)

_WEBHOOK_SECRET = (os.environ.get('WEBHOOK_SECRET') or '').strip()


def _signature_is_valid(raw_body: bytes, header: str) -> bool:
    if not _WEBHOOK_SECRET or not header:
        return False
    expected = 'sha256=' + hmac.new(
        _WEBHOOK_SECRET.encode('utf-8'), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header)


@bp.route('/api/webhook/github', methods=['POST'])
def github_webhook():
    # Sem segredo configurado → endpoint desativado (não revela detalhes)
    if not _WEBHOOK_SECRET:
        return jsonify({'success': False, 'message': 'Webhook desabilitado'}), 404

    raw_body = request.get_data() or b''
    signature = request.headers.get('X-Hub-Signature-256', '')
    if not _signature_is_valid(raw_body, signature):
        return jsonify({'success': False, 'message': 'Assinatura inválida'}), 403

    try:
        event = request.headers.get('X-GitHub-Event', '')
        if event != 'push':
            return jsonify({'success': True, 'message': f'Evento {event} ignorado'}), 200

        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': 'Dados não recebidos'}), 400

        repo_name = data.get('repository', {}).get('full_name', 'desconhecido')
        branch = data.get('ref', '').split('/')[-1] if data.get('ref') else 'unknown'
        commits = len(data.get('commits', []))

        print(f"[WEBHOOK] Push recebido: {repo_name} @ {branch} ({commits} commits)")

        result = subprocess.run(
            ['git', 'pull'],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            timeout=120,
        )
        output = result.stdout + result.stderr
        print(f"[WEBHOOK] Git pull: {output[:200]}")

        # Encerra o processo após o pull (o supervisor reinicia).
        def shutdown_and_exit():
            time.sleep(2)
            print("[WEBHOOK] Encerrando processo para reinicialização...")
            sys.stdout.flush()
            os._exit(0)

        threading.Thread(target=shutdown_and_exit, daemon=True).start()

        return jsonify({
            'success': True,
            'message': 'Webhook processado. Servidor será reiniciado.',
            'git_output': output[:500],
            'branch': branch,
            'commits': commits,
        }), 200

    except Exception as e:
        print(f"[WEBHOOK] Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
