"""Package version reported by the installed distribution metadata."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("siso-ref010")
except PackageNotFoundError:
    # A source checkout without an editable install has no distribution metadata.
    __version__ = "0+unknown"
