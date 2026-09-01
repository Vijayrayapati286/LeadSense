"""Weighted offering ↔ ICP recommendation scoring.

Final Score =
    25% ICP Fit
  + 20% Problem Fit
  + 15% Role Fit
  + 15% Industry Fit
  + 10% Company Fit
  + 10% Buying Signal Fit
  +  5% Historical Performance

Each component is 0–100. Deterministic rules decide ranking; embeddings
boost Problem Fit; LLM only fills semantic gaps / explanations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.offerings.hard_filters import passes_hard_filters
from app.offerings.models import (
    GOOD_THRESHOLD,
    HISTORICAL_NEUTRAL_SCORE,
    MATCH_TIER_GOOD,
    MATCH_TIER_POOR,
    MATCH_TIER_POTENTIAL,
    MATCH_TIER_STRONG,
    POTENTIAL_THRESHOLD,
    SCORE_WEIGHTS_V2,
    STRONG_THRESHOLD,
)
from app.offerings.scoring_utils import (
    _as_list,
    _contains_any,
    _norm,
    _parse_company_size,
    _size_overlap,
    _token_overlap,
)

# Legacy point weights (kept for older UI labels / tests that import SCORE_WEIGHTS)
SCORE_WEIGHTS = {
    "industry": 15,
    "job_title": 15,
    "department": 10,
    "company_size": 10,
    "pain_use_case": 20,
    "seniority": 10,
    "buying_signal": 10,
    "icp_fit": 25,
    "historical": 5,
}

SENIORITY_KEYWORDS = {
    "c-level": ["ceo", "cto", "coo", "cfo", "cmo", "cio", "cro", "chief"],
    "vp": ["vp", "vice president", "svp", "evp"],
    "director": ["director", "head of"],
    "manager": ["manager", "lead"],
    "individual": ["engineer", "analyst", "specialist", "associate", "coordinator"],
}

DEPARTMENT_KEYWORDS = {
    "operations": ["operations", "ops", "contact center", "call center", "bpo"],
    "sales": ["sales", "revenue", "business development", "account"],
    "customer experience": ["customer experience", "cx", "customer success", "support"],
    "hr": ["hr", "human resources", "people", "talent"],
    "engineering": ["engineering", "technology", "software", "it", "product"],
    "marketing": ["marketing", "growth", "brand"],
    "finance": ["finance", "accounting", "controller"],
}


@dataclass
class DimensionScore:
    score: int  # 0–100 for v2 components
    max: int = 100
    reason: str = ""
    matched: bool = False


@dataclass
class FitScoreResult:
    fit_score: int
    # Legacy mirrored fields (0–100 component values for storage compatibility)
    industry_score: int
    job_title_score: int
    department_score: int
    company_size_score: int
    pain_use_case_score: int
    seniority_score: int
    buying_signal_score: int
    # Spec components
    icp_fit_score: int = 0
    problem_fit_score: int = 0
    role_fit_score: int = 0
    company_fit_score: int = 0
    historical_score: int = HISTORICAL_NEUTRAL_SCORE
    semantic_similarity: int = 0
    match_tier: str = MATCH_TIER_POOR
    match_reasons: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    explanation: str = ""
    excluded: bool = False
    hard_filtered: bool = False
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)
    needs_ai_pain: bool = False
    needs_ai_title: bool = False


def _detect_seniority(title: str) -> list[str]:
    t = _norm(title)
    found = []
    for level, kws in SENIORITY_KEYWORDS.items():
        if any(k in t for k in kws):
            found.append(level)
    return found


def _detect_department(title: str, about: str = "") -> list[str]:
    blob = f"{_norm(title)} {_norm(about)}"
    found = []
    for dept, kws in DEPARTMENT_KEYWORDS.items():
        if any(k in blob for k in kws):
            found.append(dept)
    return found


def check_exclusions(offering: Any, icp: Any) -> tuple[bool, str | None]:
    exclusions = _as_list(getattr(offering, "exclusion_rules", None)) + _as_list(
        getattr(offering, "negative_keywords", None)
    )
    if not exclusions:
        return False, None
    blob = " ".join(
        [
            getattr(icp, "name", "") or "",
            getattr(icp, "company_name", "") or "",
            getattr(icp, "designation", "") or "",
            getattr(icp, "industry", "") or "",
            getattr(icp, "about", "") or "",
            getattr(icp, "location", "") or "",
        ]
    )
    hit, term = _contains_any(blob, exclusions)
    if hit:
        return True, f"Excluded by rule/keyword: {term}"
    return False, None


def score_industry_fit(offering: Any, icp: Any) -> DimensionScore:
    targets = _as_list(getattr(offering, "target_industries", None))
    industry = getattr(icp, "industry", None) or ""
    if not targets:
        return DimensionScore(40, reason="No target industries defined", matched=False)
    if not industry:
        return DimensionScore(0, reason="Candidate industry unknown", matched=False)
    hit, term = _contains_any(industry, targets)
    if hit:
        return DimensionScore(100, reason=f"Industry matches ({term})", matched=True)
    best = max((_token_overlap(industry, t) for t in targets), default=0.0)
    if best >= 0.4:
        return DimensionScore(int(100 * best), reason=f"Partial industry overlap ({industry})", matched=True)
    return DimensionScore(0, reason=f"Industry '{industry}' not in targets", matched=False)


def score_role_fit(offering: Any, icp: Any) -> DimensionScore:
    titles = _as_list(getattr(offering, "target_job_titles", None))
    seniority_targets = [_norm(t) for t in _as_list(getattr(offering, "target_seniority", None))]
    title = getattr(icp, "designation", None) or ""
    if not titles and not seniority_targets:
        return DimensionScore(30, reason="No target roles defined", matched=False)
    if not title:
        return DimensionScore(0, reason="Candidate title unknown", matched=False)

    title_pts = 0
    reasons = []
    if titles:
        hit, term = _contains_any(title, titles)
        if hit:
            title_pts = 70
            reasons.append(f"Role matches ({term})")
        else:
            best = max((_token_overlap(title, t) for t in titles), default=0.0)
            if best >= 0.45:
                title_pts = int(70 * best)
                reasons.append(f"Partial role match ({title})")

    seniority_pts = 0
    detected = _detect_seniority(title)
    if seniority_targets:
        for d in detected:
            if any(d in t or t in d or _token_overlap(d, t) >= 0.5 for t in seniority_targets):
                seniority_pts = 30
                reasons.append(f"Seniority matches ({d})")
                break
        if not seniority_pts:
            hit, term = _contains_any(title, seniority_targets)
            if hit:
                seniority_pts = 30
                reasons.append(f"Seniority signal ({term})")
    elif detected:
        seniority_pts = 15

    total = min(100, title_pts + seniority_pts)
    return DimensionScore(
        total,
        reason="; ".join(reasons) if reasons else f"Role '{title}' not in buyer personas",
        matched=total >= 40,
    )


def score_company_fit(offering: Any, icp: Any) -> DimensionScore:
    tgt_min = getattr(offering, "company_size_min", None)
    tgt_max = getattr(offering, "company_size_max", None)
    label = getattr(offering, "company_size_label", None)
    geos = _as_list(getattr(offering, "target_geographies", None))
    cand_raw = getattr(icp, "company_size", None) or ""
    location = getattr(icp, "location", None) or ""

    if label and not tgt_min and not tgt_max:
        tgt_min, tgt_max = _parse_company_size(label)
    cand_min, cand_max = _parse_company_size(cand_raw)
    size_overlap = _size_overlap(cand_min, cand_max, tgt_min, tgt_max)
    size_pts = int(70 * size_overlap)

    geo_pts = 30
    reasons = []
    if geos:
        if location:
            hit, term = _contains_any(location, geos)
            if hit:
                geo_pts = 30
                reasons.append(f"Geography matches ({term})")
            else:
                geo_pts = 0
                reasons.append("Geography outside targets")
        else:
            geo_pts = 10
            reasons.append("Geography unknown")
    else:
        geo_pts = 20

    if size_overlap >= 1.0:
        reasons.insert(0, "Company size in target range")
    elif size_overlap >= 0.3:
        reasons.insert(0, "Company size partially compatible")
    elif tgt_min is not None or tgt_max is not None:
        reasons.insert(0, "Company size outside target range")

    total = min(100, size_pts + geo_pts)
    return DimensionScore(total, reason="; ".join(reasons) or "Company fit neutral", matched=total >= 50)


def score_problem_fit(
    offering: Any,
    icp: Any,
    *,
    semantic_similarity: int = 0,
    ai_pain_score: int | None = None,
    ai_pain_reason: str | None = None,
) -> DimensionScore:
    keywords = (
        _as_list(getattr(offering, "pain_points", None))
        + _as_list(getattr(offering, "business_problems", None))
        + _as_list(getattr(offering, "use_cases", None))
        + _as_list(getattr(offering, "positive_keywords", None))
        + _as_list(getattr(offering, "desired_outcomes", None))
        + _as_list(getattr(offering, "benefits", None))
    )
    about = getattr(icp, "about", None) or ""
    title = getattr(icp, "designation", None) or ""
    blob = f"{title} {about}"

    if ai_pain_score is not None:
        # AI returns 0–100 (or legacy 0–15); normalize
        pts = int(ai_pain_score)
        if pts <= 15:
            pts = int(pts / 15 * 100)
        pts = max(0, min(100, pts))
        # Blend with semantic similarity
        blended = int(0.7 * pts + 0.3 * max(0, min(100, semantic_similarity)))
        return DimensionScore(
            blended,
            reason=ai_pain_reason or "AI semantic problem/use-case match",
            matched=blended > 0,
        )

    if not keywords:
        base = int(0.5 * max(0, min(100, semantic_similarity)))
        return DimensionScore(base, reason="No pain/use-case keywords; using semantic only", matched=base > 30)

    if not blob.strip():
        base = int(0.4 * max(0, min(100, semantic_similarity)))
        return DimensionScore(base, reason="No LinkedIn summary; weak problem signal", matched=False)

    hits = [kw for kw in keywords if _contains_any(blob, [kw])[0]]
    if hits:
        ratio = min(1.0, len(hits) / 3.0)
        kw_pts = int(70 * ratio)
    else:
        kw_pts = 0

    sem = max(0, min(100, semantic_similarity))
    total = min(100, kw_pts + int(0.3 * sem))
    reason = (
        f"Keyword overlap: {', '.join(hits[:3])}"
        if hits
        else ("Semantic problem similarity" if sem >= 40 else "No keyword pain/use-case overlap")
    )
    if sem >= 40:
        reason = f"{reason}; semantic {sem}%"
    return DimensionScore(total, reason=reason, matched=total >= 35)


def score_buying_signal(
    offering: Any,
    icp: Any,
    *,
    ai_buying_score: int | None = None,
    ai_buying_reason: str | None = None,
) -> DimensionScore:
    if ai_buying_score is not None and ai_buying_score > 0:
        pts = int(ai_buying_score)
        if pts <= 5:
            pts = int(pts / 5 * 100)
        return DimensionScore(
            max(0, min(100, pts)),
            reason=ai_buying_reason or "AI buying signal",
            matched=True,
        )

    roles = _as_list(getattr(offering, "buying_roles", None)) + _as_list(
        getattr(offering, "decision_maker_types", None)
    )
    title = getattr(icp, "designation", None) or ""
    if roles:
        hit, term = _contains_any(title, roles)
        if hit:
            return DimensionScore(100, reason=f"Buying role matches ({term})", matched=True)
        return DimensionScore(0, reason="No buying signal", matched=False)

    levels = _detect_seniority(title)
    if any(l in ("c-level", "vp", "director") for l in levels):
        return DimensionScore(60, reason="Decision-maker seniority implies buying signal", matched=True)
    return DimensionScore(20, reason="No buying role targets", matched=False)


def score_icp_fit(
    industry: DimensionScore,
    role: DimensionScore,
    company: DimensionScore,
    icp: Any,
) -> DimensionScore:
    """Overall ICP completeness / alignment composite."""
    completeness = 0
    missing = []
    if getattr(icp, "industry", None):
        completeness += 20
    else:
        missing.append("industry")
    if getattr(icp, "designation", None):
        completeness += 25
    else:
        missing.append("role")
    if getattr(icp, "company_size", None):
        completeness += 15
    else:
        missing.append("company size")
    if getattr(icp, "about", None):
        completeness += 25
    else:
        missing.append("LinkedIn summary")
    if getattr(icp, "location", None):
        completeness += 15
    else:
        missing.append("location")

    alignment = int(0.4 * industry.score + 0.4 * role.score + 0.2 * company.score)
    total = min(100, int(0.45 * completeness + 0.55 * alignment))
    reason = "ICP profile strong" if total >= 70 else "ICP profile partial"
    if missing:
        reason = f"{reason}; missing: {', '.join(missing[:3])}"
    return DimensionScore(total, reason=reason, matched=total >= 50)


def tier_for_score(score: int) -> str:
    if score >= STRONG_THRESHOLD:
        return MATCH_TIER_STRONG
    if score >= GOOD_THRESHOLD:
        return MATCH_TIER_GOOD
    if score >= POTENTIAL_THRESHOLD:
        return MATCH_TIER_POTENTIAL
    return MATCH_TIER_POOR


def build_explanation(
    *,
    overall: int,
    tier: str,
    reasons: list[str],
    missing: list[str],
    hard_filtered: bool = False,
    excluded: bool = False,
) -> str:
    if excluded or hard_filtered:
        return "Not recommended: " + (reasons[0] if reasons else "filtered out")
    lines = [f"{overall}% {tier.replace('_', ' ').title()} Match", "", "Why this match:"]
    for r in reasons[:8]:
        lines.append(f"✓ {r}")
    if missing:
        lines.append("")
        lines.append("Missing:")
        for m in missing[:5]:
            lines.append(f"⚠ {m}")
    return "\n".join(lines)


def calculate_fit_score(
    offering: Any,
    icp: Any,
    *,
    ai_pain_score: int | None = None,
    ai_pain_reason: str | None = None,
    ai_buying_score: int | None = None,
    ai_buying_reason: str | None = None,
    ai_title_boost: int = 0,
    ai_title_reason: str | None = None,
    semantic_similarity: int = 0,
    historical_score: int | None = None,
) -> FitScoreResult:
    excluded, excl_reason = check_exclusions(offering, icp)
    if excluded:
        return FitScoreResult(
            fit_score=0,
            industry_score=0,
            job_title_score=0,
            department_score=0,
            company_size_score=0,
            pain_use_case_score=0,
            seniority_score=0,
            buying_signal_score=0,
            match_tier=MATCH_TIER_POOR,
            match_reasons=[excl_reason or "Excluded"],
            explanation=build_explanation(
                overall=0, tier=MATCH_TIER_POOR, reasons=[excl_reason or "Excluded"], missing=[], excluded=True
            ),
            excluded=True,
        )

    ok, hard_reason = passes_hard_filters(offering, icp)
    if not ok:
        return FitScoreResult(
            fit_score=0,
            industry_score=0,
            job_title_score=0,
            department_score=0,
            company_size_score=0,
            pain_use_case_score=0,
            seniority_score=0,
            buying_signal_score=0,
            match_tier=MATCH_TIER_POOR,
            match_reasons=[hard_reason or "Hard filtered"],
            explanation=build_explanation(
                overall=0,
                tier=MATCH_TIER_POOR,
                reasons=[hard_reason or "Hard filtered"],
                missing=[],
                hard_filtered=True,
            ),
            hard_filtered=True,
            excluded=True,
        )

    industry = score_industry_fit(offering, icp)
    role = score_role_fit(offering, icp)
    if ai_title_boost > 0 and role.score < 100:
        boost = ai_title_boost
        if boost <= 10:
            boost = int(boost / 10 * 30)
        role = DimensionScore(
            min(100, role.score + boost),
            reason=ai_title_reason or role.reason or "AI title synonym boost",
            matched=True,
        )

    company = score_company_fit(offering, icp)
    problem = score_problem_fit(
        offering,
        icp,
        semantic_similarity=semantic_similarity,
        ai_pain_score=ai_pain_score,
        ai_pain_reason=ai_pain_reason,
    )
    buying = score_buying_signal(
        offering,
        icp,
        ai_buying_score=ai_buying_score,
        ai_buying_reason=ai_buying_reason,
    )
    icp_fit = score_icp_fit(industry, role, company, icp)
    hist = (
        HISTORICAL_NEUTRAL_SCORE
        if historical_score is None
        else max(0, min(100, int(historical_score)))
    )
    historical = DimensionScore(
        hist,
        reason="Neutral historical (insufficient feedback)" if historical_score is None else "Historical performance",
        matched=hist >= 50,
    )

    needs_ai_pain = not problem.matched and bool(getattr(icp, "about", None))
    needs_ai_title = not role.matched

    weights = SCORE_WEIGHTS_V2
    total = int(
        round(
            weights["icp_fit"] * icp_fit.score
            + weights["problem_fit"] * problem.score
            + weights["role_fit"] * role.score
            + weights["industry_fit"] * industry.score
            + weights["company_fit"] * company.score
            + weights["buying_signal"] * buying.score
            + weights["historical"] * historical.score
        )
    )
    total = max(0, min(100, total))

    # Soft must-have penalty
    must_haves = _as_list(getattr(offering, "must_have_rules", None))
    if must_haves and total > 0:
        blob = " ".join(
            [
                getattr(icp, "designation", "") or "",
                getattr(icp, "industry", "") or "",
                getattr(icp, "about", "") or "",
                getattr(icp, "company_name", "") or "",
            ]
        )
        missing_mh = [m for m in must_haves if not _contains_any(blob, [m])[0]]
        if missing_mh and len(missing_mh) == len(must_haves):
            total = max(0, total - 15)

    reasons = []
    for dim in (industry, role, company, problem, buying, icp_fit):
        if dim.matched and dim.reason:
            reasons.append(dim.reason)

    missing: list[str] = []
    if not getattr(icp, "about", None):
        missing.append("LinkedIn summary / about text")
    if not getattr(offering, "pricing_range", None):
        missing.append("Pricing suitability is unknown")
    if industry.score < 40:
        missing.append("Weak industry alignment")
    if problem.score < 35:
        missing.append("Limited pain/use-case evidence")

    tier = tier_for_score(total)
    explanation = build_explanation(overall=total, tier=tier, reasons=reasons, missing=missing)

    # Map into legacy column names (store 0–100 component values)
    return FitScoreResult(
        fit_score=total,
        industry_score=industry.score,
        job_title_score=role.score,
        department_score=icp_fit.score,  # reuse column for ICP fit
        company_size_score=company.score,
        pain_use_case_score=problem.score,
        seniority_score=role.score,  # role includes seniority
        buying_signal_score=buying.score,
        icp_fit_score=icp_fit.score,
        problem_fit_score=problem.score,
        role_fit_score=role.score,
        company_fit_score=company.score,
        historical_score=historical.score,
        semantic_similarity=max(0, min(100, int(semantic_similarity))),
        match_tier=tier,
        match_reasons=reasons or ["No strong signals"],
        missing_information=missing,
        explanation=explanation,
        dimensions={
            "icp_fit": icp_fit,
            "problem_fit": problem,
            "role_fit": role,
            "industry_fit": industry,
            "company_fit": company,
            "buying_signal": buying,
            "historical": historical,
            # legacy aliases for UI
            "industry": industry,
            "job_title": role,
            "department": icp_fit,
            "company_size": company,
            "pain_use_case": problem,
            "seniority": role,
        },
        needs_ai_pain=needs_ai_pain,
        needs_ai_title=needs_ai_title,
    )
