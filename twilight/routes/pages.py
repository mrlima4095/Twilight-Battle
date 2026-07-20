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
    if username:
        accounts = load_accounts()
        current_game = accounts.get(username, {}).get('current_game')
        if current_game and current_game in games:
            # Mesma sala (lobby ou partida) — rematch mantém o id
            return render_template('game.html', game_id=current_game, username=username)
        elif current_game:
            # sala sumiu da memória
            clear_user_game(username, current_game)
    else:
        return render_template('security/auth.html')
    return render_template('index.html')


@bp.route('/rules')
def rules(): return render_template('game/docs/rules.html')

@bp.route('/help')
def help_page(): return render_template('game/docs/help.html')


@bp.route('/story')
@login_required
def story(username): return render_template('game/story.html')


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
