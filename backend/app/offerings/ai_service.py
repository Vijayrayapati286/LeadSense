"""AI helpers for offering ICP generation and semantic match evidence."""

from __future__ import annotations

import json
import logging
import re
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
    "Do not invent fake company names. Keep lists concise (3-8 items each). "
    "suggested_name must be a short polished product/offering name (2–6 words), "
    "derived from the description — never copy the user's raw sentence, typos, "
    "or informal phrasing into suggested_name. "
    "short_description and detailed_description should expand the idea into clear "
    "professional copy; do not paste the prompt verbatim as the offering name."
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

CAMPAIGN_TYPE_SYSTEM = (
    "You are an elite B2B sales email copywriter. Given offering document content, "
    "write three DISTINCT high-level outreach emails for campaign compose: "
    "introduction, product demo invite, and follow-up. "
    "Ground each email in different facets of the offering content "
    "(value prop vs demo proof points vs reminder + next step). "
    "Always respond with valid JSON only. Use placeholders {{Name}}, {{Company}}, "
    "{{Designation}}, {{Industry}}."
)


class OfferingAIService:
    def __init__(self):
        self.settings = settings

    def generate_icp(
        self,
        description: str,
        *,
        requested_fields: list[str] | None = None,
        current_values: dict[str, Any] | None = None,
    ) -> GeneratedIcpPayload:
        if self.settings.use_mock_groq or not self.settings.groq_api_key:
            return self._mock_generate(description)

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                raw = self._groq_json(
                    system=GENERATE_SYSTEM,
                    user=self._generate_prompt(
                        description,
                        requested_fields=requested_fields,
                        current_values=current_values,
                    ),
                    temperature=0.4,
                    # gpt-oss models spend a large share of the budget on
                    # reasoning tokens; 1200 left the JSON truncated to a
                    # couple of keys with suggested_name missing.
                    max_tokens=4096,
                )
                payload = self._validate_generated(raw)
                # If the model still omitted naming fields, fill them from
                # the description so the UI never shows a blank offering name.
                if not (payload.suggested_name or "").strip():
                    payload.suggested_name = self._mock_suggested_name(description)
                if not (payload.short_description or "").strip():
                    payload.short_description = self._mock_short_description(description)
                if not (payload.detailed_description or payload.description or "").strip():
                    expanded = self._expand_mock_description(description)
                    payload.detailed_description = expanded
                    payload.description = expanded
                return payload
            except Exception as exc:
                last_err = exc
                logger.warning("Offering AI generate attempt %s failed: %s", attempt + 1, exc)
        logger.warning("Falling back to mock ICP generation: %s", last_err)
        payload = self._mock_generate(description)
        payload.is_mock = True
        return payload

    def generate_campaign_type_templates(
        self,
        *,
        offering_name: str,
        content: str,
    ) -> list[dict[str, str]]:
        """Intro / Demo / Follow-up emails grounded in synced offering docs."""
        name = (offering_name or "Our Solution").strip() or "Our Solution"
        body = (content or "").strip()
        if self.settings.use_mock_groq or not self.settings.groq_api_key:
            return self._mock_campaign_type_templates(name, body)

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                raw = self._groq_json(
                    system=CAMPAIGN_TYPE_SYSTEM,
                    user=self._campaign_type_prompt(name, body),
                    temperature=0.6,
                    max_tokens=2500,
                )
                return self._validate_campaign_type_templates(raw, name, body)
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "Campaign type email generate attempt %s failed: %s", attempt + 1, exc
                )
        logger.warning("Falling back to mock campaign type templates: %s", last_err)
        return self._mock_campaign_type_templates(name, body)

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
            model="openai/gpt-oss-120b",
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
            payload = GeneratedIcpPayload.model_validate(raw)
        except ValidationError:
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
                "selling_points",
                "positive_keywords",
                "negative_keywords",
                "must_have_rules",
                "nice_to_have_rules",
                "exclusion_rules",
            ):
                if key in raw and isinstance(raw[key], str):
                    raw[key] = [raw[key]]
            payload = GeneratedIcpPayload.model_validate(raw)
        if payload.detailed_description and not payload.description:
            payload.description = payload.detailed_description
        if payload.description and not payload.detailed_description:
            payload.detailed_description = payload.description
        return payload

    def _validate_semantic(self, raw: dict) -> SemanticMatchEvidence:
        return SemanticMatchEvidence.model_validate(raw)

    def _campaign_type_prompt(self, offering_name: str, content: str) -> str:
        clipped = (content or "").strip()[:6000] or "(no document content — invent carefully from the name only)"
        return f"""Write exactly 3 B2B cold outreach emails a lead-gen team would send.

Offering name: {offering_name}

Offering document content (source of truth — summarize into 1–2 short sentences per email; NEVER paste long raw brochure text):
---
{clipped}
---

Return JSON with key "templates" — an array of exactly 3 objects in this order:
1) type: "introduction", name: "Introduction Outreach"
2) type: "demo", name: "Product Demo Invite"
3) type: "follow_up", name: "Follow-up Email"

Rules for each object:
- subject: under 70 chars, specific to this offering + angle (not generic fluff)
- body: plain text, 80–130 words, professional lead-gen tone
- body MUST use this exact structure:
  Hi {{{{Name}}}},

  <1 short personalization line mentioning {{{{Company}}}} / {{{{Designation}}}} / {{{{Industry}}}} when natural>

  <1–2 sentences of high-level offering value — different point per email type>

  <1 soft CTA question>

  Regards,
  {{{{FromName}}}}
  Lead Generation
- Start with "Hi {{{{Name}}}}," (recipient name is merged from the contact / email local-part when missing)
- End with "Regards," then {{{{FromName}}}} on the next line, then "Lead Generation"
- Do NOT invent fake metrics. Prefer concrete capability language from the docs.
- Keep bodies short (cold-email length). Never paste raw brochure / PDF text.
- Each body must use DIFFERENT high-level points (intro = problem/fit, demo = proof, follow-up = reminder + ask)."""

    @staticmethod
    def _high_level_points(content: str, limit: int = 3) -> list[str]:
        """Pull a few short, readable sentences from offering content (not mid-string dumps)."""
        text = (content or "").replace("\r", "\n")
        # Drop markdown headings noise
        lines = []
        for line in text.split("\n"):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            lines.append(s)
        joined = " ".join(lines)
        joined = re.sub(r"\s+", " ", joined).strip()
        if not joined:
            return []
        parts = re.split(r"(?<=[.!?])\s+", joined)
        points: list[str] = []
        for part in parts:
            clean = part.strip()
            if len(clean) < 40:
                continue
            if len(clean) > 180:
                clean = clean[:177].rsplit(" ", 1)[0] + "…"
            points.append(clean)
            if len(points) >= limit:
                break
        if not points and joined:
            points.append(joined[:160].rsplit(" ", 1)[0] + ("…" if len(joined) > 160 else ""))
        return points

    @staticmethod
    def _ensure_regards_signature(body: str) -> str:
        text = (body or "").rstrip()
        if re.search(
            r"(?i)\bregards,?\s*\n\s*\{\{\s*FromName\s*\}\}(\s*\n\s*Lead Generation)?\s*$",
            text,
        ):
            if not re.search(r"(?i)Lead Generation\s*$", text):
                return f"{text}\nLead Generation"
            return text
        # Strip trailing incomplete sign-offs then append our standard close
        text = re.sub(r"(?is)\n*(thanks|best|regards|sincerely)[,!]?\s*$", "", text).rstrip()
        text = re.sub(r"(?is)\n*Lead Generation\s*$", "", text).rstrip()
        return f"{text}\n\nRegards,\n{{{{FromName}}}}\nLead Generation"

    def _mock_campaign_type_templates(
        self, offering_name: str, content: str
    ) -> list[dict[str, str]]:
        points = self._high_level_points(content, limit=3)
        while len(points) < 3:
            points.append(
                f"{offering_name} helps teams like {{{{Company}}}} move from pilots to production with clearer governance."
            )
        intro_blurb, demo_blurb, follow_blurb = points[0], points[1], points[2]
        return [
            {
                "name": "Introduction Outreach",
                "subject": f"{offering_name} for {{{{Company}}}} — quick intro",
                "body": (
                    f"Hi {{{{Name}}}},\n\n"
                    f"I reached out because {{{{Designation}}}}s in {{{{Industry}}}} "
                    f"often need a clearer path from AI experiments to production.\n\n"
                    f"{intro_blurb}\n\n"
                    f"Would you be open to a brief conversation about how this could help {{{{Company}}}}?\n\n"
                    f"Regards,\n{{{{FromName}}}}\nLead Generation"
                ),
                "template_source": "offering_ai",
            },
            {
                "name": "Product Demo Invite",
                "subject": f"15-min walkthrough of {offering_name}",
                "body": (
                    f"Hi {{{{Name}}}},\n\n"
                    f"Given your role at {{{{Company}}}}, I thought a short demo of "
                    f"{offering_name} might be useful.\n\n"
                    f"{demo_blurb}\n\n"
                    f"Would a 15-minute walkthrough this week work for you?\n\n"
                    f"Regards,\n{{{{FromName}}}}\nLead Generation"
                ),
                "template_source": "offering_ai",
            },
            {
                "name": "Follow-up Email",
                "subject": f"Following up — {offering_name} for {{{{Company}}}}",
                "body": (
                    f"Hi {{{{Name}}}},\n\n"
                    f"Just following up on {offering_name} for {{{{Company}}}} — "
                    f"happy to keep this brief.\n\n"
                    f"{follow_blurb}\n\n"
                    f"Open to a 10-minute call if useful?\n\n"
                    f"Regards,\n{{{{FromName}}}}\nLead Generation"
                ),
                "template_source": "offering_ai",
            },
        ]

    def _validate_campaign_type_templates(
        self, raw: dict, offering_name: str, content: str
    ) -> list[dict[str, str]]:
        items = raw.get("templates") or raw.get("versions") or []
        if not isinstance(items, list) or len(items) < 3:
            raise ValueError("AI response missing 3 campaign templates")
        expected = [
            ("introduction", "Introduction Outreach"),
            ("demo", "Product Demo Invite"),
            ("follow_up", "Follow-up Email"),
        ]
        out: list[dict[str, str]] = []
        for idx, (etype, ename) in enumerate(expected):
            item = items[idx] if isinstance(items[idx], dict) else {}
            subject = str(item.get("subject") or "").strip()
            body = self._ensure_regards_signature(str(item.get("body") or "").strip())
            if not subject or not body:
                raise ValueError(f"AI template missing subject/body for {ename}")
            if "{{Name}}" not in body and "{{name}}" not in body:
                body = f"Hi {{{{Name}}}},\n\n{body}"
            out.append(
                {
                    "name": ename,
                    "subject": subject,
                    "body": body,
                    "template_source": "offering_ai",
                    "type": str(item.get("type") or etype),
                }
            )
        bodies = {t["body"] for t in out}
        if len(bodies) < 2:
            return self._mock_campaign_type_templates(offering_name, content)
        return out

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

    def _generate_prompt(
        self,
        description: str,
        *,
        requested_fields: list[str] | None = None,
        current_values: dict[str, Any] | None = None,
    ) -> str:
        requested = ", ".join(requested_fields or []) or "all fields"
        context = json.dumps(current_values or {}, ensure_ascii=False)[:3000]
        return f"""Analyze this offering and return a single JSON object.
Priority keys (always include these first):
suggested_name, short_description, detailed_description, description, product_type,
target_customer, pricing_range.

Then also include:
industries (array), company_size (object with min, max, label),
departments, job_titles, seniority, geographies, business_models,
decision_maker_types, buying_roles, pain_points, business_problems,
use_cases, desired_outcomes, benefits, selling_points, positive_keywords, negative_keywords,
must_have_rules, nice_to_have_rules, exclusion_rules.

Requested fields: {requested}
Current offering context (keep suggestions coherent, but do not merely copy it):
{context}

Offering description:
{description.strip()}

Rules for naming/copy:
- suggested_name: invent a concise product name based on the offering (not the raw prompt text).
- short_description: one professional sentence summarizing the offering.
- detailed_description: 2–4 sentences expanding what it does and who it helps.
- Never set suggested_name equal to the offering description prompt.
"""

    def _semantic_prompt(self, offering: Any, icp: Any) -> str:
        return f"""Score semantic fit. Max pain_use_case_score=100, buying_signal_score=100, job_title_boost=30.
Return JSON keys: pain_use_case_score, pain_use_case_reason, buying_signal_score,
buying_signal_reason, job_title_boost, job_title_reason.

Offering name: {getattr(offering, 'name', '')}
Offering description: {getattr(offering, 'short_description', '') or getattr(offering, 'description', '')}
Product/service type: {getattr(offering, 'product_type', '')}
Target customer: {getattr(offering, 'target_customer', '')}
Target industries: {getattr(offering, 'target_industries', [])}
Pain points: {getattr(offering, 'pain_points', [])}
Current challenges: {getattr(offering, 'current_challenges', [])}
Use cases: {getattr(offering, 'use_cases', [])}
Benefits: {getattr(offering, 'benefits', [])}
Selling points: {getattr(offering, 'selling_points', [])}
Target titles: {getattr(offering, 'target_job_titles', [])}
Target departments: {getattr(offering, 'target_departments', [])}
Target seniority: {getattr(offering, 'target_seniority', [])}

Candidate name: {getattr(icp, 'name', '')}
Title: {getattr(icp, 'designation', '')}
Company: {getattr(icp, 'company_name', '')}
Industry: {getattr(icp, 'industry', '')}
About: {(getattr(icp, 'about', '') or '')[:800]}
"""

    @staticmethod
    def _normalize_prompt(description: str) -> str:
        return " ".join((description or "").strip().split())

    @classmethod
    def _detect_mock_domain(cls, description: str) -> str:
        lower = (description or "").lower()
        if any(
            phrase in lower
            for phrase in (
                "commercial banking",
                "commercial lending",
                "working capital",
                "equipment financing",
                "banking",
                "bank ",
                "lending",
                "loan",
            )
        ):
            return "banking"
        if any(w in lower for w in ("crm", "customer relationship", "sales force", "salesforce")):
            return "crm"
        if any(w in lower for w in ("call", "contact center", "bpo", "coaching", "qa")):
            return "call"
        if any(w in lower for w in ("hr", "human resource", "talent", "recruit")):
            return "hr"
        if any(w in lower for w in ("market", "campaign", "lead gen")):
            return "marketing"
        if any(w in lower for w in ("analytic", "dashboard", "bi ", "business intelligence")):
            return "analytics"
        return "general"

    @classmethod
    def _mock_suggested_name(cls, description: str) -> str:
        """Invent a concise product-style offering name from a rough prompt.

        Never echo the raw sentence the user typed — that belongs in the
        description fields, not suggested_name.
        """
        domain = cls._detect_mock_domain(description)
        names = {
            "banking": "Banking Growth Platform",
            "crm": "Sales CRM Platform",
            "call": "AI Call Copilot",
            "hr": "Talent Operations Suite",
            "marketing": "Demand Generation Platform",
            "analytics": "Revenue Analytics Suite",
            "general": "Business Workflow Platform",
        }
        return names.get(domain, names["general"])

    @classmethod
    def _mock_short_description(cls, description: str) -> str:
        domain = cls._detect_mock_domain(description)
        shorts = {
            "banking": "Lending and relationship tools for modern banking and commercial finance teams.",
            "crm": "CRM software that helps sales teams track pipeline, accounts, and follow-ups.",
            "call": "AI-powered call coaching and conversation intelligence for contact centers.",
            "hr": "HR workflows that help people teams hire, retain, and support employees.",
            "marketing": "Campaign and lead tools that help marketing teams create demand.",
            "analytics": "Analytics that help revenue teams see pipeline and performance clearly.",
            "general": "B2B software that helps teams streamline operations and improve outcomes.",
        }
        return shorts.get(domain, shorts["general"])

    @classmethod
    def _expand_mock_description(cls, description: str, *, domain_hint: str | None = None) -> str:
        """Turn a short prompt into a full detailed description (mock mode only).

        Real Groq generation expands prompts; mock must invent coherent copy
        instead of pasting the user's rough sentence into every field.
        """
        text = cls._normalize_prompt(description)
        if not text:
            return (
                "A B2B solution that helps teams streamline operations, "
                "improve visibility, and drive better outcomes."
            )
        # User already wrote a full description — keep it.
        if len(text) >= 120:
            return text

        domain = cls._detect_mock_domain(text)
        hint = domain_hint or {
            "banking": "banking and financial-services",
            "crm": "CRM / sales",
            "call": "contact-center",
            "hr": "HR / people-ops",
            "marketing": "marketing",
            "analytics": "analytics",
            "general": "B2B software",
        }.get(domain, "B2B software")

        return (
            f"This {hint} offering helps teams run day-to-day work more effectively. "
            f"Based on the buyer's need around \"{text}\", it addresses gaps in visibility, "
            f"manual effort, and inconsistent processes. Teams use it to track progress, "
            f"collaborate across roles, reduce busywork, and scale with a clearer operating "
            f"picture and stronger customer outcomes."
        )

    def _mock_generate(self, description: str) -> GeneratedIcpPayload:
        lower = description.lower()
        prompt = self._normalize_prompt(description)
        domain = self._detect_mock_domain(description)
        is_banking = domain == "banking"
        is_crm = domain == "crm"
        is_call = domain == "call"

        if is_banking:
            detailed = self._expand_mock_description(
                description,
                domain_hint="banking and financial-services",
            )
            # Preserve the known banking fixture name when the prompt is clearly
            # the commercial-lending scenario used in tests / demos.
            rich_banking = any(
                phrase in lower
                for phrase in ("commercial banking", "commercial lending", "working capital", "equipment financing")
            )
            return GeneratedIcpPayload(
                industries=["Banking", "Financial Services", "Commercial Lending"],
                company_size={"min": 200, "max": 10000, "label": "200-10000 employees"},
                departments=["Commercial Banking", "Business Banking", "Lending"],
                job_titles=[
                    "Commercial Banker",
                    "Commercial Banking Relationship Manager",
                    "Business Banking Manager",
                    "Corporate Banking Manager",
                    "Commercial Lending Manager",
                ],
                seniority=["Manager", "Director", "VP"],
                business_models=["B2B", "Financial Services"],
                decision_maker_types=["Relationship manager", "Commercial banking leader"],
                buying_roles=["Decision maker", "Advisor"],
                pain_points=[
                    "Difficulty identifying suitable financing products",
                    "Complex business financing requirements",
                    "Customer retention challenges",
                    "Limited visibility into customer financing needs",
                ],
                business_problems=["Complex financing decisions", "Limited portfolio growth"],
                use_cases=[
                    "Working capital financing",
                    "Business expansion",
                    "Equipment financing",
                    "Commercial lending",
                    "Portfolio growth",
                ],
                desired_outcomes=["More lending opportunities", "Stronger customer relationships"],
                benefits=[
                    "Personalized financing solutions",
                    "Improved customer relationships",
                    "Increased lending opportunities",
                    "Stronger commercial banking portfolios",
                ],
                selling_points=[
                    "Flexible financing options",
                    "Customized lending recommendations",
                    "Relationship-led portfolio growth",
                ],
                positive_keywords=["commercial banking", "lending", "working capital", "portfolio growth"],
                negative_keywords=["consumer banking", "personal loans"],
                suggested_name=(
                    "Commercial Business Growth & Lending Solutions"
                    if rich_banking
                    else self._mock_suggested_name(prompt)
                ),
                short_description=(
                    "Flexible commercial lending solutions for businesses seeking financing "
                    "for growth and working capital."
                    if rich_banking
                    else self._mock_short_description(prompt)
                ),
                description=detailed,
                detailed_description=detailed,
                product_type="Financial Services",
                target_customer="Commercial banks, business banking teams and financial institutions.",
                pricing_range="Contact sales",
                is_mock=True,
            )

        if is_crm:
            detailed = self._expand_mock_description(description, domain_hint="CRM / sales")
            return GeneratedIcpPayload(
                industries=["SaaS", "Technology", "Enterprise Software"],
                company_size={"min": 50, "max": 5000, "label": "50-5000"},
                departments=["Sales", "Revenue", "Customer Success"],
                job_titles=["VP Sales", "CRO", "Head of Revenue", "Sales Director", "Sales Manager"],
                seniority=["C-level", "VP", "Director", "Manager"],
                geographies=["United States", "Europe", "India"],
                business_models=["B2B", "SaaS"],
                decision_maker_types=["Economic buyer", "Champion"],
                buying_roles=["Decision maker", "Influencer"],
                pain_points=["Scattered customer data", "Manual pipeline tracking", "Low forecast accuracy"],
                business_problems=["Pipeline leakage", "Inconsistent follow-up", "Weak CRM adoption"],
                use_cases=["Lead tracking", "Opportunity management", "Account visibility"],
                desired_outcomes=["Higher win rates", "Cleaner pipeline", "Faster follow-up"],
                benefits=["Centralized contacts", "Pipeline visibility", "Team collaboration"],
                selling_points=["Fast setup", "Sales-friendly workflows", "Clear reporting"],
                positive_keywords=["crm", "sales", "pipeline", "accounts"],
                negative_keywords=["student", "intern", "freelancer"],
                must_have_rules=["Sales or revenue leadership"],
                nice_to_have_rules=["Existing CRM or spreadsheet-based tracking"],
                exclusion_rules=["Individual contributor only", "Unrelated industry"],
                suggested_name=self._mock_suggested_name(prompt),
                short_description=self._mock_short_description(prompt),
                description=detailed,
                detailed_description=detailed,
                product_type="SaaS",
                target_customer="B2B sales and revenue teams that need clearer pipeline and account visibility",
                pricing_range="Contact sales",
                is_mock=True,
            )

        industries = ["BPO", "Contact Centers", "SaaS", "Telecom"] if is_call else ["SaaS", "Technology", "Enterprise Software"]
        titles = (
            ["COO", "VP Operations", "Head of Customer Experience", "Contact Center Director", "Sales Director"]
            if is_call
            else ["VP Sales", "CRO", "Head of Revenue", "Sales Director", "COO"]
        )
        if is_call:
            detailed = (
                "An AI platform that analyzes customer calls, provides real-time coaching, "
                "and evaluates agent performance for contact centers and BPOs."
            )
            suggested_name = self._mock_suggested_name(prompt)
            short_description = self._mock_short_description(prompt)
            target_customer = "Contact center and BPO operations teams"
        else:
            detailed = self._expand_mock_description(description, domain_hint="B2B software")
            suggested_name = self._mock_suggested_name(prompt)
            short_description = self._mock_short_description(prompt)
            target_customer = "B2B teams seeking better workflow visibility and outcomes"

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
            selling_points=["Fast implementation", "Actionable team insights", "Scalable workflows"],
            positive_keywords=["call quality", "contact center", "agent performance", "QA"] if is_call else ["sales", "revenue", "pipeline"],
            negative_keywords=["student", "intern", "freelancer"],
            must_have_rules=["Operations or sales leadership"],
            nice_to_have_rules=["Existing QA or coaching program"],
            exclusion_rules=["Individual contributor only", "Unrelated industry"],
            suggested_name=suggested_name,
            short_description=short_description,
            description=detailed,
            detailed_description=detailed,
            product_type="SaaS",
            target_customer=target_customer,
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
