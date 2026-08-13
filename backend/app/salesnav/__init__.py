"""LinkedIn Sales Navigator extraction module (LeadSense).

Isolated feature package: Playwright session checks, viewport screenshots +
backend OCR for single profiles, Apify search extraction, and Excel export.
"""

from app.salesnav.routes import router

__all__ = ["router"]
