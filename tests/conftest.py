from pathlib import Path

import pytest

from siso_ref010 import EntityTypeCatalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def catalog():
    return EntityTypeCatalog.bundled()
