"""Registro de blueprints HTTP."""


def register_blueprints(app):
    from twilight.routes import admin, auth, games, journal, pages, story, webhook

    app.register_blueprint(pages.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(games.bp)
    app.register_blueprint(story.bp)
    app.register_blueprint(journal.bp)
    app.register_blueprint(webhook.bp)
    app.register_blueprint(admin.bp)
