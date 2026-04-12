"""Ollama LLM provider — Gemma 4 via local Ollama instance."""

import json

import httpx

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
from app.logging_config import get_logger

logger = get_logger(__name__)


class OllamaProvider(LLMProvider):
    """LLM provider using a local Ollama instance with Gemma 4."""

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.keep_alive = settings.ollama_keep_alive

    async def _chat(
        self,
        system: str,
        user_message: str,
        tools: list[dict] | None = None,
    ) -> dict:
        """Send a chat request to Ollama and return the response."""
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()

    def _extract_tool_call(self, response: dict, tool_name: str) -> dict | None:
        """Extract arguments from the first matching tool call in the response."""
        message = response.get("message", {})
        tool_calls = message.get("tool_calls", [])
        for tc in tool_calls:
            fn = tc.get("function", {})
            if fn.get("name") == tool_name:
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)
                return args

        # Fallback: try to parse the content as JSON if no tool call was made
        content = message.get("content", "")
        if content:
            try:
                parsed = json.loads(content)
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

        response = await self._chat(
            system=ROLE_CLASSIFICATION_SYSTEM,
            user_message=user_msg,
            tools=ROLE_CLASSIFICATION_TOOLS,
        )

        args = self._extract_tool_call(response, "classify_person_role")
        if not args:
            logger.warning("llm.role_classification.no_tool_call", provider="ollama")
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

        response = await self._chat(
            system=CONTENT_ANALYSIS_SYSTEM,
            user_message=user_msg,
            tools=CONTENT_ANALYSIS_TOOLS,
        )

        args = self._extract_tool_call(response, "annotate_content")
        if not args:
            logger.warning("llm.content_analysis.no_tool_call", provider="ollama")
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
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                # Check if our model (or a prefix of it) is available
                model_base = self.model.split(":")[0]
                return any(model_base in m for m in models)
        except Exception:
            return False
