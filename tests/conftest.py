from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def pdf_fixtures(tmp_path_factory):
    path = Path(__file__).parent / "fixtures" / "generate.py"
    spec = importlib.util.spec_from_file_location("synthetic_pdf_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate(tmp_path_factory.mktemp("pdf-fixtures"))
