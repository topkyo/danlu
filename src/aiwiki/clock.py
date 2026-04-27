from __future__ import annotations

import datetime as _datetime

__all__ = ["utc_now"]


def utc_now() -> _datetime.datetime:
    return _datetime.datetime.now(_datetime.timezone.utc)
