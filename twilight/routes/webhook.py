"""Webhooks externos (Forgejo/GitHub)."""
from flask import Blueprint, jsonify, request
import subprocess
import sys
import threading
import time

bp = Blueprint('webhook', __name__)


@bp.route('/api/webhook/github', methods=['POST'])
def github_webhook():
    try:
        # Verificar token de segurança (opcional)
        # auth_token = request.headers.get('X-Hub-Signature-256', '')
        # expected_token = open("webhook.txt", "r").read().strip()
        
        # Verificar se é um evento de push
        event = request.headers.get('X-GitHub-Event', '')
        if event != 'push': 
            return jsonify({'success': True, 'message': f'Evento {event} ignorado'}), 200
        
        # Obter dados do webhook
        data = request.get_json()
        if not data: 
            return jsonify({'success': False, 'message': 'Dados não recebidos'}), 400
        
        repo_name = data.get('repository', {}).get('full_name', 'desconhecido')
        branch = data.get('ref', '').split('/')[-1] if data.get('ref') else 'unknown'
        commits = len(data.get('commits', []))
        
        # Verificar se é a branch correta (opcional)
        # if branch != 'main' and branch != 'master':
        #     print(f"[WEBHOOK] Branch {branch} ignorada")
        #     return jsonify({'success': True, 'message': f'Branch {branch} ignorada'}), 200
        
        print(f"[WEBHOOK] Push recebido do GitHub: {repo_name} @ {branch} ({commits} commits)")
        
        # Executar git pull
        result = subprocess.run(['git', 'pull'], capture_output=True, text=True, 
                              cwd=os.path.dirname(os.path.abspath(__file__)))
        
        output = result.stdout + result.stderr
        print(f"[WEBHOOK] Git pull: {output[:200]}")
        
        
        # ENCERRAR O PROCESSO - systemd vai reiniciar
        def shutdown_and_exit():
            time.sleep(2)
            print("[WEBHOOK] Encerrando processo para reinicialização pelo systemd...")
            sys.stdout.flush()
            os._exit(0)
        
        threading.Thread(target=shutdown_and_exit, daemon=True).start()
        
        return jsonify({
            'success': True,
            'message': 'Webhook do GitHub processado. Servidor será reiniciado pelo systemd.',
            'git_output': output[:500] if len(output) > 500 else output,
            'branch': branch,
            'commits': commits
        }), 200
        
    except Exception as e:
        print(f"[WEBHOOK] Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# Socket.IO events

