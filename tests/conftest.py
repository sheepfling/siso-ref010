from pathlib import Path

import pytest

from siso_entity_type import SisoEnums

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def catalog():
    return SisoEnums.bundled()
