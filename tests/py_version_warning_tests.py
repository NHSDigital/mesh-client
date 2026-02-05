import importlib
import sys

import pytest


def test_deprecation_warning_on_python_lt_310(monkeypatch):
    # Simulate Python 3.9 to trigger the import-time warning
    monkeypatch.setattr(sys, "version_info", (3, 9, 15, "final", 0))
    sys.modules.pop("mesh_client", None)
    with pytest.warns(DeprecationWarning, match="python versions < 3.10 are end of life and no longer supported."):
        importlib.import_module("mesh_client")
