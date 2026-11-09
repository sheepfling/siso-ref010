from pathlib import Path

import pytest

from siso_ref010 import ReferenceCatalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def catalog():
    return ReferenceCatalog.bundled()
