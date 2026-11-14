"""Bound expensive password work per process, including unauthenticated registrations."""

import threading

from fastapi import HTTPException
from pwdlib import PasswordHash

_hash = PasswordHash.recommended()
_slots = threading.BoundedSemaphore(4)


def _run(function, *args):
    if not _slots.acquire(blocking=False):
        raise HTTPException(
            429,
            "Přihlašování je momentálně vytížené. Zkuste to za chvíli.",
            headers={"Retry-After": "1"},
        )
    try:
        return function(*args)
    finally:
        _slots.release()


def hash_password(password):
    return _run(_hash.hash, password)


def verify_password(password, encoded):
    return _run(_hash.verify, password, encoded)
