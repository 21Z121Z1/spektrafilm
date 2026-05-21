from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Iterator


_METAL_RUNTIME_LOCK = RLock()


@contextmanager
def serialized_metal_runtime() -> Iterator[None]:
    """Serialize MLX/Metal runtime work across GUI and worker threads."""
    with _METAL_RUNTIME_LOCK:
        yield
