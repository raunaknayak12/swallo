"""Initial scaffold sanity test."""

import swallo


def test_version_present() -> None:
    assert swallo.__version__ is not None
    assert len(swallo.__version__) > 0
