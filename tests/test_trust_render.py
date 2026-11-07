"""Regression checks for public bundle assembly; no Talos secrets are used."""

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "clusters/trust/render.py"
spec = importlib.util.spec_from_file_location("trust_render", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TrustRenderTests(unittest.TestCase):
    def test_rejects_crlf_without_normalizing_it(self) -> None:
        with TemporaryDirectory() as directory:
            patches = Path(directory)
            cluster = patches / "cluster"
            cluster.mkdir()
            (cluster / "hostname.yaml").write_bytes(
                b"apiVersion: v1alpha1\r\nkind: HostnameConfig\r\nhostname: test\r\n"
            )
            with patch.object(module, "PATCHES", patches):
                with self.assertRaisesRegex(ValueError, "LF-terminated"):
                    module.render()

    def test_rejects_duplicate_document_identity(self) -> None:
        with TemporaryDirectory() as directory:
            patches = Path(directory)
            cluster = patches / "cluster"
            cluster.mkdir()
            for name in ("first", "second"):
                (cluster / f"{name}.yaml").write_text(
                    "apiVersion: v1alpha1\nkind: HostnameConfig\nhostname: test\n"
                )
            with patch.object(module, "PATCHES", patches):
                with self.assertRaisesRegex(ValueError, "Duplicate Talos document"):
                    module.render()

    def test_committed_bundle_matches_sources(self) -> None:
        self.assertEqual(module.RENDERED.read_bytes(), module.render())


if __name__ == "__main__":
    unittest.main()
