"""OpenAI email generation service with mock fallback."""

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
        Generate a professional sales email using OpenAI or mock data.

        Returns: subject, body, closing, cta, is_mock
        """
        if self.settings.use_mock_openai or not self.settings.openai_api_key:
            return self._mock_generate(campaign_data)

        try:
            return self._openai_generate(campaign_data)
        except Exception as exc:
            logger.warning("OpenAI generation failed, using mock: %s", exc)
            result = self._mock_generate(campaign_data)
            result["is_mock"] = True
            return result

    def _openai_generate(self, campaign_data: dict) -> dict:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)

        prompt = self._build_prompt(campaign_data)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional B2B sales email copywriter. "
                        "Generate concise, formal, personalized cold outreach emails. "
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

Requirements:
- Catchy but professional subject line
- Short email body (3-4 paragraphs max)
- Use {{{{Name}}}}, {{{{Company}}}}, {{{{Designation}}}} placeholders for personalization
- Include a clear CTA
- Formal tone
- Return JSON with keys: subject, body, closing, cta"""

    def _mock_generate(self, campaign_data: dict) -> dict:
        name = campaign_data.get("campaign_name", "Your Product")
        audience = campaign_data.get("target_audience", "business leaders")

        return {
            "subject": f"Unlock Growth Opportunities for {{{{Company}}}} — Exclusive Offer Inside",
            "body": (
                f"Dear {{{{Name}}}},\n\n"
                f"I hope this message finds you well. As {{{{Designation}}}} at {{{{Company}}}}, "
                f"you understand the challenges of reaching {audience} effectively.\n\n"
                f"We've helped companies in the {{{{Industry}}}} sector achieve remarkable results "
                f"with our {name} solution. Our clients typically see a 40% improvement in "
                f"engagement within the first quarter.\n\n"
                f"I'd love to share how we can tailor this approach specifically for {{{{Company}}}}. "
                f"Would you be open to a brief 15-minute call this week?"
            ),
            "closing": "Best regards,\nSales Team",
            "cta": "Schedule a 15-minute discovery call",
            "is_mock": True,
        }
