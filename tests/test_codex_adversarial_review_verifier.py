from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.verify_codex_adversarial_review_fixes import (  # noqa: E402
    check_android_jni_guards,
    check_grain_local_rng,
    check_pipeline_backend_key,
)


class VerifierSourceChecksTest(unittest.TestCase):
    def _repo(self):
        temp = tempfile.TemporaryDirectory()
        repo = Path(temp.name)
        self.addCleanup(temp.cleanup)
        return repo

    def test_pipeline_check_rejects_missing_backend_comparison(self):
        repo = self._repo()
        path = repo / "src" / "spektrafilm" / "runtime" / "pipeline.py"
        path.parent.mkdir(parents=True)
        path.write_text(
            "class SimulationPipeline:\n"
            "    def __init__(self):\n"
            "        self._lut_service = previous_lut_service\n",
        )

        failures = check_pipeline_backend_key(repo)

        self.assertTrue(any("backend cache key" in failure for failure in failures), failures)

    def test_grain_check_rejects_global_seed_without_local_rng(self):
        repo = self._repo()
        path = repo / "src" / "spektrafilm" / "model" / "grain.py"
        path.parent.mkdir(parents=True)
        path.write_text(
            "import numpy as np\n"
            "def layer_particle_model(seed=None):\n"
            "    if seed is not None:\n"
            "        np.random.seed(seed)\n",
        )

        failures = check_grain_local_rng(repo)

        self.assertTrue(any("local RNG" in failure for failure in failures), failures)

    def test_android_check_rejects_missing_short_json_guard(self):
        repo = self._repo()
        path = repo / "android" / "app" / "src" / "main" / "cpp" / "spektrafilm_android_jni.cpp"
        path.parent.mkdir(parents=True)
        path.write_text(
            "float extract_json_float(const char* json, size_t len, const char* key, float def) {\n"
            "    size_t klen = strlen(key);\n"
            "    for (size_t i = 0; i < len - klen; i++) return def;\n"
            "}\n",
        )

        failures = check_android_jni_guards(repo)

        self.assertTrue(any("short JSON" in failure for failure in failures), failures)


if __name__ == "__main__":
    unittest.main()
