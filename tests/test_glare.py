from types import SimpleNamespace

import numpy as np

from spektrafilm.model import glare as glare_module


def test_add_glare_passes_backend_and_keeps_backend_math(monkeypatch) -> None:
    class FakeBackend:
        supports_gpu = True

        def __init__(self) -> None:
            self.asarray_calls = 0

        def asarray(self, value):
            self.asarray_calls += 1
            return np.asarray(value, dtype=np.float32)

    backend = FakeBackend()
    captured: dict[str, object] = {}

    def fake_compute_random_glare_amount(amount, roughness, blur, shape, backend=None):
        captured.update(
            amount=amount,
            roughness=roughness,
            blur=blur,
            shape=shape,
            backend=backend,
        )
        return np.full(shape, 0.1, dtype=np.float32)

    monkeypatch.setattr(
        glare_module,
        "compute_random_glare_amount",
        fake_compute_random_glare_amount,
    )

    xyz = np.zeros((2, 3, 3), dtype=np.float32)
    illuminant_xyz = np.array([1.0, 0.5, 0.25], dtype=np.float32)
    glare = SimpleNamespace(active=True, percent=0.03, roughness=0.7, blur=0.5)

    result = glare_module.add_glare(xyz, illuminant_xyz, glare, backend=backend)

    assert captured == {
        "amount": 0.03,
        "roughness": 0.7,
        "blur": 0.5,
        "shape": (2, 3),
        "backend": backend,
    }
    assert backend.asarray_calls == 1
    np.testing.assert_allclose(result[0, 0], [0.1, 0.05, 0.025])
