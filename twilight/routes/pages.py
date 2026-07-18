"""Páginas HTML principais."""
from flask import Blueprint, redirect, render_template

from twilight.auth.service import get_current_user, load_accounts, login_required, update_user_game
from twilight.state import games

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    username = get_current_user()
    if username:
        accounts = load_accounts()
        current_game = accounts.get(username, {}).get('current_game')
        if current_game and current_game in games:
            return render_template('game.html', game_id=current_game, username=username)
    else:
        return render_template('auth.html')
    return render_template('index.html')


@bp.route('/rules')
def rules():
    return render_template('rules.html')


@bp.route('/help')
def help_page():
    return render_template('help.html')


@bp.route('/story')
@login_required
def story(username):
    return render_template('story.html')


@bp.route('/journal')
def journal():
    username = get_current_user()
    if not username:
        return redirect('/')
    return render_template('journal.html', username=username)


@bp.route('/game/<game_id>')
@login_required
def game(username, game_id):
    if game_id not in games:
        return redirect("/")

    update_user_game(username, game_id)

    return render_template('game.html', game_id=game_id, username=username)


@bp.route('/spectate/<game_id>')
@login_required
def spectate_game(username, game_id):
    if game_id not in games:
        return redirect("/")

    return render_template('spectate.html', game_id=game_id, username=username)
