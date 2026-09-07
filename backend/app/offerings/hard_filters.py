"""Configurable hard filters before weighted scoring."""

from __future__ import annotations

from typing import Any

from app.offerings.models import DEFAULT_HARD_FILTER_RULES
from app.offerings.scoring_utils import (
    _as_list,
    _contains_any,
    _norm,
    _parse_company_size,
    _size_overlap,
    _token_overlap,
)


def resolve_hard_filter_rules(offering: Any) -> dict[str, Any]:
    rules = dict(DEFAULT_HARD_FILTER_RULES)
    custom = getattr(offering, "hard_filter_rules", None) or {}
    if isinstance(custom, dict):
        rules.update({k: v for k, v in custom.items() if k in DEFAULT_HARD_FILTER_RULES or k.startswith("require_")})
    return rules


def passes_hard_filters(offering: Any, icp: Any) -> tuple[bool, str | None]:
    """Return (ok, reason). Failures mean the offering must not be recommended."""
    rules = resolve_hard_filter_rules(offering)

    if rules.get("require_industry_overlap"):
        targets = _as_list(getattr(offering, "target_industries", None))
        industry = getattr(icp, "industry", None) or ""
        if targets and industry:
            hit, _ = _contains_any(industry, targets)
            best = max((_token_overlap(industry, t) for t in targets), default=0.0)
            if not hit and best < 0.35:
                return False, f"Hard filter: industry '{industry}' not in offering targets"

    if rules.get("require_geography_overlap"):
        geos = _as_list(getattr(offering, "target_geographies", None))
        location = getattr(icp, "location", None) or ""
        if geos and location:
            hit, _ = _contains_any(location, geos)
            if not hit:
                return False, f"Hard filter: location '{location}' outside target geographies"

    if rules.get("require_company_size_overlap"):
        tgt_min = getattr(offering, "company_size_min", None)
        tgt_max = getattr(offering, "company_size_max", None)
        label = getattr(offering, "company_size_label", None)
        if label and tgt_min is None and tgt_max is None:
            tgt_min, tgt_max = _parse_company_size(label)
        cand_min, cand_max = _parse_company_size(getattr(icp, "company_size", None))
        if (tgt_min is not None or tgt_max is not None) and (
            cand_min is not None or cand_max is not None
        ):
            if _size_overlap(cand_min, cand_max, tgt_min, tgt_max) <= 0:
                return False, "Hard filter: company size outside target range"

    if rules.get("require_role_overlap"):
        titles = _as_list(getattr(offering, "target_job_titles", None))
        designation = getattr(icp, "designation", None) or ""
        min_overlap = float(rules.get("min_role_token_overlap") or 0.4)
        if titles and designation:
            hit, _ = _contains_any(designation, titles)
            best = max((_token_overlap(designation, t) for t in titles), default=0.0)
            if not hit and best < min_overlap:
                return False, f"Hard filter: role '{designation}' not in target titles"

    return True, None
