"""24-hour URL-hash cache for profile extraction results."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.profile_extractor.models import ProfileExtractCache
from app.profile_extractor.validator import url_hash

logger = logging.getLogger(__name__)

CACHE_HOURS = 24


class ProfileCacheService:
    def get(self, db: Session, profile_url: str) -> dict[str, str | None] | None:
        digest = url_hash(profile_url)
        now = datetime.now(timezone.utc)
        row = (
            db.query(ProfileExtractCache)
            .filter(
                ProfileExtractCache.url_hash == digest,
                ProfileExtractCache.expires_at > now,
            )
            .first()
        )
        if not row:
            return None
        try:
            data = json.loads(row.result_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return {
            "full_name": data.get("full_name"),
            "company": data.get("company"),
            "designation": data.get("designation"),
            "about": data.get("about"),
        }

    def set(self, db: Session, profile_url: str, result: dict[str, Any]) -> None:
        digest = url_hash(profile_url)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=CACHE_HOURS)
        payload = json.dumps(
            {
                "full_name": result.get("full_name"),
                "company": result.get("company"),
                "designation": result.get("designation"),
                "about": result.get("about"),
            }
        )
        row = (
            db.query(ProfileExtractCache)
            .filter(ProfileExtractCache.url_hash == digest)
            .first()
        )
        if row:
            row.result_json = payload
            row.profile_url = profile_url
            row.expires_at = expires
        else:
            db.add(
                ProfileExtractCache(
                    url_hash=digest,
                    profile_url=profile_url,
                    result_json=payload,
                    expires_at=expires,
                )
            )
        db.commit()
        logger.info("Cached profile extract url_hash=%s…", digest[:12])
