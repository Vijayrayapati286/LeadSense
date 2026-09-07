"""LinkedIn Profile Extractor module (LeadSense).

Isolated, reusable package: Playwright primary + Apify fallback for
Full Name / Company / Designation / About only. Never exposes cookies
to the frontend.
"""

from app.linkedin.routes import router

__all__ = ["router"]
