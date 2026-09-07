"""Shared text/normalization helpers for scoring and hard filters."""

from __future__ import annotations

import re
from typing import Any


def _norm(value: str | None) -> str:
    if not value:
        return ""
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9\s+/&-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _token_overlap(a: str, b: str) -> float:
    ta = set(_norm(a).split())
    tb = set(_norm(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _contains_any(haystack: str, needles: list[str]) -> tuple[bool, str | None]:
    h = _norm(haystack)
    for n in needles:
        nn = _norm(n)
        if not nn:
            continue
        if nn in h or _token_overlap(h, nn) >= 0.6:
            return True, n
    return False, None


def _parse_company_size(raw: str | None) -> tuple[int | None, int | None]:
    if not raw:
        return None, None
    text = raw.lower().replace(",", "").replace("employees", "").strip()
    m = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s*\+", text)
    if m:
        return int(m.group(1)), None
    m = re.search(r"(\d+)", text)
    if m:
        n = int(m.group(1))
        return n, n
    return None, None


def _size_overlap(
    cand_min: int | None,
    cand_max: int | None,
    tgt_min: int | None,
    tgt_max: int | None,
) -> float:
    if tgt_min is None and tgt_max is None:
        return 0.5
    if cand_min is None and cand_max is None:
        return 0.3
    c_lo = cand_min if cand_min is not None else 0
    c_hi = cand_max if cand_max is not None else 10**9
    t_lo = tgt_min if tgt_min is not None else 0
    t_hi = tgt_max if tgt_max is not None else 10**9
    if c_hi < t_lo or c_lo > t_hi:
        return 0.0
    return 1.0
