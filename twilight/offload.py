"""Executa trabalho bloqueante fora do loop de eventos do gevent.

hashlib.pbkdf2_hmac libera o GIL, mas ainda é CPU-bound; urlopen é IO síncrono.
Rodar num pool pequeno evita travar todos os sockets do worker único.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='twilight-offload')


def run_offloop(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return _pool.submit(fn, *args, **kwargs).result()
