"""Saves do modo história em data/saves/."""
import os

from twilight.config import SAVES_DIR, ensure_data_dirs


def get_user_save_file(username):
    ensure_data_dirs()
    return os.path.join(SAVES_DIR, f'{username}_story_save.json')
