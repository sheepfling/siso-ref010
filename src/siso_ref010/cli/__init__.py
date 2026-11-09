"""Command-line adapter, kept separate from the Python API."""

from .app import main
from .text import render_diff_summary

__all__ = ["main", "render_diff_summary"]
