"""Re-query MillionVerifier for given addresses (skips cache).

Usage:
  python scripts/reverify_emails.py a@x.com b@y.com
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import SessionLocal, init_db
from app.models import EmailVerification
from app.services.millionverifier_service import (
    MillionVerifierService,
    classify_cached_verification,
    is_display_risky,
)


def main(emails: list[str]) -> int:
    init_db()
    svc = MillionVerifierService()
    db = SessionLocal()
    try:
        print("email\tresult\tquality\tlabel\tallowed\tcan_include_risky")
        for raw in emails:
            email = raw.strip().lower()
            if not email:
                continue
            db.query(EmailVerification).filter(EmailVerification.email == email).delete()
            db.commit()
            gate = svc.verify_email(db, email)
            db.commit()
            label = classify_cached_verification(gate.quality, gate.result) or gate.result or ""
            include_risky = is_display_risky(gate.quality, gate.result)
            print(
                f"{email}\t{gate.result or ''}\t{gate.quality or ''}\t{label}\t"
                f"{'yes' if gate.allowed else 'no'}\t{'yes' if include_risky else 'no'}"
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/reverify_emails.py email [email ...]", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
