"""Anthropic LLM provider — Claude API fallback."""

import json
import logging

from app.config import settings
from app.llm.prompts import (
    CONTENT_ANALYSIS_SYSTEM,
    CONTENT_ANALYSIS_TOOLS,
    ROLE_CLASSIFICATION_SYSTEM,
    ROLE_CLASSIFICATION_TOOLS,
)
from app.llm.provider import (
    ContentAnalysisResult,
    ContentAnnotation,
    LLMProvider,
    RoleClassification,
    SentenceClassification,
)

logger = logging.getLogger(__name__)


def _ollama_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert Ollama-style tool definitions to Anthropic format."""
    result = []
    for tool in tools:
        fn = tool.get("function", {})
        result.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {}),
        })
    return result


class AnthropicProvider(LLMProvider):
    """LLM provider using the Anthropic API as a fallback."""

    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    async def _chat(
        self,
        system: str,
        user_message: str,
        tools: list[dict] | None = None,
    ) -> dict | None:
        """Send a message and extract the first tool_use block's input."""
        kwargs: dict = {
            "model": self.model,
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": "user", "content": user_message}],
        }
        if tools:
            kwargs["tools"] = _ollama_tools_to_anthropic(tools)
            kwargs["tool_choice"] = {"type": "auto"}

        response = await self.client.messages.create(**kwargs)

        for block in response.content:
            if block.type == "tool_use":
                return block.input

        # Fallback: try parsing text content as JSON
        for block in response.content:
            if block.type == "text" and block.text.strip():
                try:
                    parsed = json.loads(block.text)
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
        return None

    async def classify_role(
        self,
        person_name: str,
        surrounding_context: str,
        document_type: str | None = None,
    ) -> RoleClassification:
        user_msg = (
            f"Beoordeel de volgende persoonsnaam:\n\n"
            f"Naam: {person_name}\n"
            f"Context: ...{surrounding_context}...\n"
        )
        if document_type:
            user_msg += f"Documenttype: {document_type}\n"

        args = await self._chat(
            system=ROLE_CLASSIFICATION_SYSTEM,
            user_message=user_msg,
            tools=ROLE_CLASSIFICATION_TOOLS,
        )

        if not args:
            logger.warning("No tool call in Anthropic role classification response")
            return RoleClassification(
                role="citizen",
                should_redact=True,
                confidence=0.5,
                reason_nl="Automatische classificatie niet mogelijk — standaard als burger behandeld.",
            )

        return RoleClassification(
            role=args.get("role", "citizen"),
            should_redact=args.get("should_redact", True),
            confidence=min(max(float(args.get("confidence", 0.5)), 0.0), 1.0),
            reason_nl=args.get("reason_nl", ""),
        )

    async def analyze_content(
        self,
        passage: str,
        document_type: str | None = None,
        surrounding_context: str | None = None,
    ) -> ContentAnalysisResult:
        user_msg = f"Analyseer de volgende passage:\n\n{passage}\n"
        if document_type:
            user_msg += f"\nDocumenttype: {document_type}"
        if surrounding_context:
            user_msg += f"\nOmringende context: ...{surrounding_context}..."

        args = await self._chat(
            system=CONTENT_ANALYSIS_SYSTEM,
            user_message=user_msg,
            tools=CONTENT_ANALYSIS_TOOLS,
        )

        if not args:
            logger.warning("No tool call in Anthropic content analysis response")
            return ContentAnalysisResult(
                summary_nl="Automatische analyse niet mogelijk voor deze passage."
            )

        annotations = [
            ContentAnnotation(
                woo_article=a.get("woo_article", ""),
                label_nl=a.get("label_nl", ""),
                analysis_nl=a.get("analysis_nl", ""),
                likelihood=a.get("likelihood", "low"),
            )
            for a in args.get("annotations", [])
        ]

        sentence_classifications = [
            SentenceClassification(
                sentence=s.get("sentence", ""),
                classification=s.get("classification", "mixed"),
                explanation_nl=s.get("explanation_nl", ""),
            )
            for s in args.get("sentence_classifications", [])
        ]

        return ContentAnalysisResult(
            annotations=annotations,
            sentence_classifications=sentence_classifications,
            summary_nl=args.get("summary_nl", ""),
        )

    async def health_check(self) -> bool:
        try:
            # Simple models list call to check connectivity
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return len(response.content) > 0
        except Exception:
            return False
