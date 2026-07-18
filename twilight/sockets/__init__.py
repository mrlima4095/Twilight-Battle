"""Socket.IO — importar handlers registra os eventos no socketio."""


def register_socket_handlers():
    # side-effect import: @socketio.on decorators
    from twilight.sockets import handlers  # noqa: F401
