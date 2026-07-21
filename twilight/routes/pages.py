"""Páginas HTML principais."""
from flask import Blueprint, redirect, render_template

from twilight.auth.service import (
    clear_user_game,
    get_current_user,
    load_accounts,
    login_required,
    update_user_game,
)
from twilight.state import games

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    username = get_current_user()
    if not username:
        return render_template('security/auth.html')

    # Limpa ponteiro se a sala morreu; NÃO força a página da partida aqui —
    # o jogador pode abrir o lobby em outra aba e voltar com o link/código.
    accounts = load_accounts()
    current_game = accounts.get(username, {}).get('current_game')
    if current_game and current_game not in games:
        clear_user_game(username, current_game)
        current_game = None

    return render_template(
        'index.html',
        active_game_id=current_game if current_game in games else None,
    )


@bp.route('/rules')
def rules(): return render_template('game/docs/rules.html')

@bp.route('/help')
def help_page(): return render_template('game/docs/help.html')

@bp.route('/lore')
def lore_page():
    """Crônica / lore do mundo (docs/lore.md → templates/game/docs/lore.html)."""
    return render_template('game/docs/lore.html')

@bp.route('/tutorial')
@login_required
def tutorial_page(username):
    """Página de entrada do tutorial (inicia 1v1 com o Mentor)."""
    return render_template('game/docs/tutorial.html', username=username)


@bp.route('/story')
@login_required
def story(username): return render_template('game/story.html')


@bp.route('/story/rules')
def story_rules():
    """Regras do Modo História (RPG) — separado do multiplayer de cartas."""
    return render_template('game/docs/story_rules.html')


@bp.route('/story/help')
def story_help():
    """Ajuda / FAQ do Modo História — separado do multiplayer de cartas."""
    return render_template('game/docs/story_help.html')


@bp.route('/journal')
def journal():
    username = get_current_user()
    if not username:
        return redirect('/')
    return render_template('web/journal.html', username=username)


@bp.route('/game/<game_id>')
@login_required
def game(username, game_id):
    if game_id not in games:
        clear_user_game(username, game_id)
        return redirect("/")

    # Rematch: sala continua existindo (lobby ou partida)
    update_user_game(username, game_id)

    return render_template('game/game.html', game_id=game_id, username=username)


@bp.route('/spectate/<game_id>')
@login_required
def spectate_game(username, game_id):
    if game_id not in games:
        return redirect("/")

    return render_template('game/spectate.html', game_id=game_id, username=username)
