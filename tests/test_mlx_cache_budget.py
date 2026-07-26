from __future__ import annotations

import pytest

from spektrafilm.gpu import mlx_cache


pytestmark = pytest.mark.unit


class _FakeMx:
    def __init__(self, cache_bytes: int) -> None:
        self.cache_bytes = cache_bytes
        self.clear_calls = 0

    def clear_cache(self) -> None:
        self.clear_calls += 1

    def get_cache_memory(self) -> int:
        return self.cache_bytes


class _FakeBackend:
    def __init__(self, mx: _FakeMx) -> None:
        self.mx = mx


def test_default_budget_is_zero_clear_every_call(monkeypatch) -> None:
    monkeypatch.delenv("SPEKTRAFILM_MLX_CACHE_CLEAR_BUDGET_MB", raising=False)
    assert mlx_cache.cache_clear_budget_bytes() == 0

    fake = _FakeMx(cache_bytes=1)
    mlx_cache.maybe_clear_cache(_FakeBackend(fake))
    assert fake.clear_calls == 1


def test_env_budget_gates_small_caches(monkeypatch) -> None:
    monkeypatch.setenv("SPEKTRAFILM_MLX_CACHE_CLEAR_BUDGET_MB", "256")
    assert mlx_cache.cache_clear_budget_bytes() == 256 * 1024 * 1024

    below = _FakeMx(cache_bytes=255 * 1024 * 1024)
    mlx_cache.maybe_clear_cache(_FakeBackend(below))
    assert below.clear_calls == 0

    above = _FakeMx(cache_bytes=257 * 1024 * 1024)
    mlx_cache.maybe_clear_cache(_FakeBackend(above))
    assert above.clear_calls == 1


def test_invalid_env_budget_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("SPEKTRAFILM_MLX_CACHE_CLEAR_BUDGET_MB", "not-a-number")
    assert mlx_cache.cache_clear_budget_bytes() == 0


def test_missing_cache_probe_clears_conservatively(monkeypatch) -> None:
    monkeypatch.setenv("SPEKTRAFILM_MLX_CACHE_CLEAR_BUDGET_MB", "256")

    class _NoProbe:
        def __init__(self) -> None:
            self.clear_calls = 0

        def clear_cache(self) -> None:
            self.clear_calls += 1

    fake = _NoProbe()
    mlx_cache.maybe_clear_cache(fake)
    assert fake.clear_calls == 1


def test_objects_without_clear_cache_are_ignored() -> None:
    mlx_cache.maybe_clear_cache(object())
