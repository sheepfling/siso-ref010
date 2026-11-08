from pathlib import Path

import pytest

from dis_entity_types import EntityTypeCatalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def catalog():
    return EntityTypeCatalog.bundled()
