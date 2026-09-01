"""The HTTP surface: the embeddable API, and the setup page that configures it."""

from .app import create_app

__all__ = ["create_app"]
