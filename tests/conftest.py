from pathlib import Path

import pytest

from siso_ref010.catalog import ReferenceCatalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def catalog() -> ReferenceCatalog:
    # Catalog behavior assertions use the v37 golden source edition.
    return ReferenceCatalog.bundled(37)
