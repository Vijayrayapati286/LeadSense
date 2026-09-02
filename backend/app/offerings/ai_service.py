"""AI helpers for offering ICP generation and semantic match evidence."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.offerings.schemas import (
    GeneratedIcpPayload,
    GenerateOfferingEmailRequest,
    OfferingEmailVersion,
    SemanticMatchEvidence,
)

logger = logging.getLogger(__name__)
settings = get_settings()

GENERATE_SYSTEM = (
    "You are a B2B go-to-market analyst. Given a product/service description, "
    "produce a structured Ideal Customer Profile (ICP) and buyer persona as JSON only. "
    "Do not invent fake company names. Keep lists concise (3-8 items each)."
)

SEMANTIC_SYSTEM = (
    "You are a B2B ICP matching analyst. Compare an offering against one candidate. "
    "Return JSON only with scores that MUST stay within the stated maximums. "
    "Do not invent facts not present in the candidate text."
)

EMAIL_SYSTEM = (
    "You are an elite B2B sales email copywriter. Write punchy, executive-level cold "
    "outreach emails with clear structure: short paragraphs, bold emphasis, and scannable "
    "bullet lists. Always respond with valid JSON only."
)


class OfferingAIService:
    def __init__(self):
        self.settings = settings

    def generate_icp(self, description: str) -> GeneratedIcpPayload:
        if self.settings.use_mock_groq or not self.settings.groq_api_key:
            return self._mock_generate(description)

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                raw = self._groq_json(
                    system=GENERATE_SYSTEM,
                    user=self._generate_prompt(description),
                    temperature=0.4,
                    max_tokens=1200,
                )
                return self._validate_generated(raw)
            except Exception as exc:
                last_err = exc
                logger.warning("Offering AI generate attempt %s failed: %s", attempt + 1, exc)
        logger.warning("Falling back to mock ICP generation: %s", last_err)
        payload = self._mock_generate(description)
        payload.is_mock = True
        return payload

    def generate_email_templates(self, data: GenerateOfferingEmailRequest) -> dict:
        """Generate 2–3 distinct outreach email variants from offering context."""
        if self.settings.use_mock_groq or not self.settings.groq_api_key:
            return self._mock_email_templates(data)

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                raw = self._groq_json(
                    system=EMAIL_SYSTEM,
                    user=self._email_prompt(data),
                    temperature=0.75,
                    max_tokens=2000,
                )
                return self._validate_email_templates(raw, data.count)
            except Exception as exc:
                last_err = exc
                logger.warning("Offering email generate attempt %s failed: %s", attempt + 1, exc)
        logger.warning("Falling back to mock email templates: %s", last_err)
        result = self._mock_email_templates(data)
        result["is_mock"] = True
        return result

    def semantic_evidence(self, offering: Any, icp: Any) -> SemanticMatchEvidence:
        if self.settings.use_mock_groq or not self.settings.groq_api_key:
            return self._mock_semantic(offering, icp)

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                raw = self._groq_json(
                    system=SEMANTIC_SYSTEM,
                    user=self._semantic_prompt(offering, icp),
                    temperature=0.2,
                    max_tokens=500,
                )
                return self._validate_semantic(raw)
            except Exception as exc:
                last_err = exc
                logger.warning("Semantic match attempt %s failed: %s", attempt + 1, exc)
        logger.warning("Semantic match falling back to empty evidence: %s", last_err)
        return SemanticMatchEvidence()

    def _groq_json(self, *, system: str, user: str, temperature: float, max_tokens: int) -> dict:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("AI response is not a JSON object")
        return data

    def _validate_generated(self, raw: dict) -> GeneratedIcpPayload:
        # Normalize nested company_size
        cs = raw.get("company_size") or {}
        if isinstance(cs, str):
            raw["company_size"] = {"label": cs}
        try:
            return GeneratedIcpPayload.model_validate(raw)
        except ValidationError as exc:
            # coerce common list/string mistakes
            for key in (
                "industries",
                "departments",
                "job_titles",
                "seniority",
                "geographies",
                "business_models",
                "decision_maker_types",
                "buying_roles",
                "pain_points",
                "business_problems",
                "use_cases",
                "desired_outcomes",
                "benefits",
                "positive_keywords",
                "negative_keywords",
                "must_have_rules",
                "nice_to_have_rules",
                "exclusion_rules",
            ):
                if key in raw and isinstance(raw[key], str):
                    raw[key] = [raw[key]]
            return GeneratedIcpPayload.model_validate(raw)

    def _validate_semantic(self, raw: dict) -> SemanticMatchEvidence:
        return SemanticMatchEvidence.model_validate(raw)

    def _email_prompt(self, data: GenerateOfferingEmailRequest) -> str:
        def join(items: list[str]) -> str:
            return ", ".join(items) if items else "N/A"

        return f"""Generate exactly {data.count} different B2B cold outreach emails for this offering.

Offering: {data.name}
Description: {data.description or data.short_description or 'N/A'}
Product type: {data.product_type or 'N/A'}
Target industries: {join(data.target_industries)}
Target job titles: {join(data.target_job_titles)}
Geographies: {join(data.target_geographies)}
Company size: {data.company_size_label or 'N/A'}
Pain points: {join(data.pain_points)}
Use cases: {join(data.use_cases)}
Benefits: {join(data.benefits)}
Desired outcomes: {join(data.desired_outcomes)}
Decision makers: {join(data.decision_maker_types)}
Buying roles: {join(data.buying_roles)}
Tone: {data.tone}
Additional context: {data.additional_context or 'None'}

Return JSON with key "versions" — an array of exactly {data.count} objects, each with:
- angle: one of "pain_led", "benefit_led", "direct"
- subject: under 80 chars, provocative hook (not generic)
- body: plain text with markdown (**bold**, "- " bullets). Start with "Hi {{{{Name}}}}," then blank line.
  Use {{{{Name}}}}, {{{{Company}}}}, {{{{Designation}}}}, {{{{Industry}}}} placeholders.
  Under ~160 words excluding bullets. Include one 3-5 item benefit bullet list in benefit_led version.
- closing: sign-off line
- cta: soft call-to-action question

Each version must use a distinctly different opening angle."""

    def _validate_email_templates(self, raw: dict, count: int) -> dict:
        versions_raw = raw.get("versions") or []
        if not isinstance(versions_raw, list):
            raise ValueError("AI response missing versions array")
        versions: list[OfferingEmailVersion] = []
        for item in versions_raw[:count]:
            if not isinstance(item, dict):
                continue
            versions.append(
                OfferingEmailVersion(
                    angle=str(item.get("angle") or "direct"),
                    subject=str(item.get("subject") or "").strip(),
                    body=str(item.get("body") or "").strip(),
                    closing=str(item.get("closing") or "").strip(),
                    cta=str(item.get("cta") or "").strip(),
                )
            )
        if len(versions) < 2:
            raise ValueError("AI returned fewer than 2 email versions")
        return {"versions": [v.model_dump() for v in versions], "is_mock": False}

    def _mock_email_templates(self, data: GenerateOfferingEmailRequest) -> dict:
        name = data.name or "Your Product"
        industry = (data.target_industries or ["your industry"])[0]
        pain = (data.pain_points or ["manual workflows"])[0]
        benefit = (data.benefits or ["faster results"])[0]
        use_case = (data.use_cases or ["workflow automation"])[0]

        versions = [
            OfferingEmailVersion(
                angle="pain_led",
                subject=f"Hidden cost of {pain.lower()} at {{{{Company}}}}",
                body=(
                    f"Hi {{{{Name}}}},\n\n"
                    f"Most {{{{Designation}}}}s at {{{{Industry}}}} companies face **{pain.lower()}** — "
                    f"and it rarely shows up on the dashboard until it hurts the pipeline.\n\n"
                    f"**{name}** was built for teams like {{{{Company}}}} dealing with exactly this.\n\n"
                    f"Worth a quick 15-minute look?"
                ),
                closing="Best regards,",
                cta="Open to a brief call this week?",
            ),
            OfferingEmailVersion(
                angle="benefit_led",
                subject=f"{benefit} for {{{{Company}}}} — {name}",
                body=(
                    f"Hi {{{{Name}}}},\n\n"
                    f"Teams in {industry} use **{name}** to unlock:\n\n"
                    f"- **{benefit}** through {use_case.lower()}\n"
                    f"- **Better visibility** for {{{{Designation}}}}s managing growth\n"
                    f"- **Faster outcomes** without adding headcount\n\n"
                    f"Given your role at {{{{Company}}}}, I thought this might resonate. "
                    f"Can I share a quick overview?"
                ),
                closing="Best regards,",
                cta="Would a 15-minute demo work?",
            ),
            OfferingEmailVersion(
                angle="direct",
                subject=f"Quick intro — {name} for {{{{Company}}}}",
                body=(
                    f"Hi {{{{Name}}}},\n\n"
                    f"I help {{{{Designation}}}}s at {industry} companies with **{name}** — "
                    f"{data.short_description or data.description or use_case.lower()}.\n\n"
                    f"Open to a short conversation to see if it's a fit for {{{{Company}}}}?"
                ),
                closing="Best regards,",
                cta="Worth 15 minutes?",
            ),
        ]
        selected = versions[: data.count]
        return {"versions": [v.model_dump() for v in selected], "is_mock": True}

    def _generate_prompt(self, description: str) -> str:
        return f"""Analyze this offering and return JSON with exactly these keys:
industries (array), company_size (object with min, max, label),
departments, job_titles, seniority, geographies, business_models,
decision_maker_types, buying_roles, pain_points, business_problems,
use_cases, desired_outcomes, benefits, positive_keywords, negative_keywords,
must_have_rules, nice_to_have_rules, exclusion_rules,
suggested_name, short_description, product_type.

Offering description:
{description.strip()}
"""

    def _semantic_prompt(self, offering: Any, icp: Any) -> str:
        return f"""Score semantic fit. Max pain_use_case_score=100, buying_signal_score=100, job_title_boost=30.
Return JSON keys: pain_use_case_score, pain_use_case_reason, buying_signal_score,
buying_signal_reason, job_title_boost, job_title_reason.

Offering name: {getattr(offering, 'name', '')}
Offering description: {getattr(offering, 'short_description', '') or getattr(offering, 'description', '')}
Pain points: {getattr(offering, 'pain_points', [])}
Use cases: {getattr(offering, 'use_cases', [])}
Target titles: {getattr(offering, 'target_job_titles', [])}

Candidate name: {getattr(icp, 'name', '')}
Title: {getattr(icp, 'designation', '')}
Company: {getattr(icp, 'company_name', '')}
Industry: {getattr(icp, 'industry', '')}
About: {(getattr(icp, 'about', '') or '')[:800]}
"""

    def _mock_generate(self, description: str) -> GeneratedIcpPayload:
        lower = description.lower()
        is_call = any(w in lower for w in ("call", "contact center", "bpo", "coaching", "qa"))
        industries = ["BPO", "Contact Centers", "SaaS", "Telecom"] if is_call else ["SaaS", "Technology", "Enterprise Software"]
        titles = (
            ["COO", "VP Operations", "Head of Customer Experience", "Contact Center Director", "Sales Director"]
            if is_call
            else ["VP Sales", "CRO", "Head of Revenue", "Sales Director", "COO"]
        )
        return GeneratedIcpPayload(
            industries=industries,
            company_size={"min": 200, "max": 5000, "label": "200-5000"},
            departments=["Operations", "Sales", "Customer Experience"] if is_call else ["Sales", "Revenue", "Operations"],
            job_titles=titles,
            seniority=["C-level", "VP", "Director"],
            geographies=["United States", "India", "Philippines"] if is_call else ["United States", "Europe", "India"],
            business_models=["B2B", "SaaS"],
            decision_maker_types=["Economic buyer", "Champion"],
            buying_roles=["Decision maker", "Influencer"],
            pain_points=(
                ["Inconsistent call quality", "Manual coaching doesn't scale", "Agent performance opacity"]
                if is_call
                else ["Low conversion rates", "Manual workflows", "Lack of visibility"]
            ),
            business_problems=(
                ["Quality assurance backlog", "High attrition", "Inconsistent CSAT"]
                if is_call
                else ["Pipeline leakage", "Slow sales cycles"]
            ),
            use_cases=(
                ["Real-time call coaching", "Automated QA scoring", "Conversation intelligence"]
                if is_call
                else ["Revenue analytics", "Workflow automation"]
            ),
            desired_outcomes=["Higher CSAT", "Faster ramp", "Lower QA cost"] if is_call else ["Higher win rates", "Faster deals"],
            benefits=["AI coaching", "Automated evaluation", "Manager dashboards"],
            positive_keywords=["call quality", "contact center", "agent performance", "QA"] if is_call else ["sales", "revenue", "pipeline"],
            negative_keywords=["student", "intern", "freelancer"],
            must_have_rules=["Operations or sales leadership"],
            nice_to_have_rules=["Existing QA or coaching program"],
            exclusion_rules=["Individual contributor only", "Unrelated industry"],
            suggested_name="AI Call Copilot" if is_call else "AI Sales Platform",
            short_description=(
                "AI-powered call coaching and conversation intelligence"
                if is_call
                else "AI-powered platform for B2B sales teams"
            ),
            description=(
                "An AI platform that analyzes customer calls, provides real-time coaching, "
                "and evaluates agent performance for contact centers and BPOs."
                if is_call
                else "An AI platform that helps B2B sales teams improve conversion and pipeline visibility."
            ),
            product_type="SaaS",
            pricing_range="Contact sales",
            is_mock=True,
        )

    def _mock_semantic(self, offering: Any, icp: Any) -> SemanticMatchEvidence:
        title = (getattr(icp, "designation", "") or "").lower()
        about = (getattr(icp, "about", "") or "").lower()
        blob = f"{title} {about}"
        pain = 0
        reason = "No semantic overlap detected"
        keywords = ["quality", "coaching", "call", "contact center", "agent", "qa", "performance", "sales", "revenue"]
        hits = [k for k in keywords if k in blob]
        if hits:
            pain = min(100, 30 + 15 * len(hits))
            reason = f"Role text relates to: {', '.join(hits[:4])}"
        boost = 0
        title_reason = ""
        targets = [str(t).lower() for t in (getattr(offering, "target_job_titles", None) or [])]
        if any(any(tok in title for tok in t.split() if len(tok) > 3) for t in targets):
            boost = 20
            title_reason = "Title semantically aligns with buyer persona"
        buying = 60 if any(w in title for w in ("vp", "director", "head", "chief", "coo", "cro")) else 0
        return SemanticMatchEvidence(
            pain_use_case_score=pain,
            pain_use_case_reason=reason,
            buying_signal_score=buying,
            buying_signal_reason="Decision-maker level title" if buying else "",
            job_title_boost=boost,
            job_title_reason=title_reason,
        )


offering_ai_service = OfferingAIService()
