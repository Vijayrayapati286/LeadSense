"""Compatibility shim — Sales Navigator lives in app.salesnav."""

from app.salesnav.routes import router

__all__ = ["router"]
