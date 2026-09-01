"""Offering / ICP embedding helpers (no separate vector DB).

Uses deterministic hash embeddings in mock mode so tests stay offline.
When GROQ/OpenAI key is available, prefers a remote embedding API if configured;
otherwise falls back to the local hash embedding (still useful for cosine boost).
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Any, Sequence

from app.config import get_settings
from app.offerings.scoring_utils import _as_list

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_DIM = 64
EMBEDDING_MODEL_LOCAL = "local-hash-v1"


def build_offering_profile_text(offering: Any) -> str:
    parts = [
        getattr(offering, "name", None) or "",
        getattr(offering, "short_description", None) or "",
        getattr(offering, "description", None) or "",
        "Industries: " + ", ".join(_as_list(getattr(offering, "target_industries", None))),
        "Roles: " + ", ".join(_as_list(getattr(offering, "target_job_titles", None))),
        "Problems: " + ", ".join(_as_list(getattr(offering, "pain_points", None))),
        "Problems: " + ", ".join(_as_list(getattr(offering, "business_problems", None))),
        "Use cases: " + ", ".join(_as_list(getattr(offering, "use_cases", None))),
        "Benefits: " + ", ".join(_as_list(getattr(offering, "benefits", None))),
        "Keywords: " + ", ".join(_as_list(getattr(offering, "positive_keywords", None))),
        "Buying: " + ", ".join(_as_list(getattr(offering, "buying_roles", None))),
    ]
    return "\n".join(p for p in parts if p and str(p).strip())


def build_icp_profile_text(icp: Any) -> str:
    parts = [
        getattr(icp, "name", None) or "",
        getattr(icp, "designation", None) or "",
        getattr(icp, "company_name", None) or "",
        getattr(icp, "industry", None) or "",
        getattr(icp, "company_size", None) or "",
        getattr(icp, "location", None) or "",
        getattr(icp, "about", None) or "",
    ]
    return "\n".join(p for p in parts if p and str(p).strip())


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def local_hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic bag-of-tokens embedding (unit-normalized)."""
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vec[idx] += sign * weight
    return _l2_normalize(vec)


def _l2_normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return [0.0] * len(vec)
    return [v / norm for v in vec]


def cosine_similarity(a: Sequence[float] | None, b: Sequence[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def embed_text(text: str) -> tuple[list[float], str]:
    """Return (embedding, model_name). Always available offline via local hash."""
    # Prefer local deterministic embeddings for reliability / mock mode.
    # Remote embedding APIs can be plugged here later without schema changes.
    _ = settings  # reserved for future API key routing
    return local_hash_embedding(text), EMBEDDING_MODEL_LOCAL


def ensure_offering_embedding(offering: Any) -> list[float]:
    profile = build_offering_profile_text(offering)
    offering.profile_text = profile
    vec, model = embed_text(profile)
    offering.embedding = vec
    offering.embedding_model = model
    return vec


def ensure_icp_embedding(icp: Any) -> list[float]:
    existing = getattr(icp, "embedding", None)
    if isinstance(existing, list) and existing:
        return existing
    vec, model = embed_text(build_icp_profile_text(icp))
    icp.embedding = vec
    icp.embedding_model = model
    return vec


def semantic_similarity_score(offering: Any, icp: Any) -> int:
    """0–100 similarity between offering profile and ICP (esp. about/summary)."""
    off_vec = getattr(offering, "embedding", None)
    if not off_vec:
        off_vec = ensure_offering_embedding(offering)
    icp_vec = ensure_icp_embedding(icp)
    sim = cosine_similarity(off_vec, icp_vec)
    # Map cosine [-1,1] roughly [0,1] for these unit vectors → [0,100]
    return max(0, min(100, int(round((sim + 1) / 2 * 100))))
