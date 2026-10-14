"""Send one LeadSense test email to Sunhith.

Usage (from backend folder, or inside the backend container):
  python scripts/send_to_sunhith.py
  python scripts/send_to_sunhith.py sunhith.45@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from send_test_mail import main

DEFAULT_TO = "sunhith.musuku@feuji.com"

if __name__ == "__main__":
    to_email = sys.argv[1].strip() if len(sys.argv) > 1 else DEFAULT_TO
    sys.exit(main(to_email))
