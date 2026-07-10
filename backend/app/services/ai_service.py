"""Groq email generation service with mock fallback."""

import json
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AIService:
    def __init__(self):
        self.settings = settings

    def generate_email(self, campaign_data: dict) -> dict:
        """
        Generate a professional sales email using Groq or mock data.

        Returns: subject, body, closing, cta, is_mock
        """
        if self.settings.use_mock_groq or not self.settings.groq_api_key:
            return self._mock_generate(campaign_data)

        try:
            return self._groq_generate(campaign_data)
        except Exception as exc:
            logger.warning("Groq generation failed, using mock: %s", exc)
            result = self._mock_generate(campaign_data)
            result["is_mock"] = True
            return result

    def _groq_generate(self, campaign_data: dict) -> dict:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        prompt = self._build_prompt(campaign_data)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an elite B2B sales email copywriter, in the style of top SaaS "
                        "growth teams. You write punchy, executive-level cold outreach emails "
                        "with clear visual structure: short paragraphs, a bolded phrase or two "
                        "for emphasis, and a scannable bullet list of concrete benefits. "
                        "Always respond with valid JSON containing: subject, body, closing, cta."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=800,
        )

        content = response.choices[0].message.content
        result = json.loads(content)
        return {
            "subject": result.get("subject", ""),
            "body": result.get("body", ""),
            "closing": result.get("closing", ""),
            "cta": result.get("cta", ""),
            "is_mock": False,
        }

    def _build_prompt(self, campaign_data: dict) -> str:
        return f"""Generate a professional B2B sales cold email with the following details:

Campaign Name: {campaign_data.get('campaign_name', 'N/A')}
Description: {campaign_data.get('campaign_description', 'N/A')}
Target Audience: {campaign_data.get('target_audience', 'Business professionals')}
Tone: {campaign_data.get('tone', 'formal')}
Additional Context: {campaign_data.get('additional_context', 'None')}

Formatting requirements for the "body" field (this is critical, follow exactly):
- Write plain text using a small markdown subset: wrap 2-4 key phrases or
  stats in **double asterisks** for emphasis, and write benefit lists as
  separate lines each starting with "- ".
- Separate every paragraph and the bullet list from each other with a blank
  line (i.e. two newlines).
- Start with "Hi {{{{Name}}}}," on its own line, then a blank line.
- Open with a short, sharp 1-2 sentence hook naming a hidden problem the
  audience faces — not a generic "I hope this finds you well" greeting.
- Follow with one short paragraph naming the specific pain, with the key
  phrase in **bold**.
- Include exactly one bulleted list of 3-5 concrete, quantified benefits,
  each item leading with a **bold phrase** followed by the detail.
- Close with one short paragraph containing a bolded outcome or number,
  ending in a soft CTA question (e.g. "Worth a quick look?").
- Keep the body under ~160 words excluding the bullet list.
- Use {{{{Name}}}}, {{{{Company}}}}, {{{{Designation}}}}, {{{{Industry}}}}
  placeholders for personalization.

Other requirements:
- Subject: a short, provocative hook (under 80 characters) that names a
  hidden problem — not a generic sales subject line.
- Formal but energetic tone.
- Return JSON with keys: subject, body, closing, cta"""

    def _mock_generate(self, campaign_data: dict) -> dict:
        name = campaign_data.get("campaign_name", "Your Product")
        audience = campaign_data.get("target_audience", "business leaders")

        return {
            "subject": f"Your Metrics Are Green. Your {audience.title()} Disagree.",
            "body": (
                f"Hi {{{{Name}}}},\n\n"
                f"Most teams like {{{{Company}}}} look successful on paper — targets hit, "
                f"dashboards green.\n\n"
                f"**But behind those green metrics**, {{{{Designation}}}}s are often stuck "
                f"fighting manual work, rising costs, and slipping {audience} engagement.\n\n"
                f"We've helped {{{{Industry}}}} teams fix this with {name}:\n\n"
                f"- **40% faster turnaround** through automated workflows\n"
                f"- **25-30% cost reduction** by eliminating manual busywork\n"
                f"- **Real-time visibility** across every stage, not just the dashboard\n\n"
                f"With this approach, **{{{{Company}}}} could unlock meaningful capacity within "
                f"a single quarter**. Worth a quick 15-minute look?"
            ),
            "closing": "Best,\nSales Team",
            "cta": "Schedule a 15-minute discovery call",
            "is_mock": True,
        }
