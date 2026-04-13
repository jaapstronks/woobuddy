"""Abstract LLM provider interface.

The project only ships a local Ollama implementation — document text must
never be sent to third-party hosted models. The abstraction remains in place
so alternative local backends can be swapped in without touching callers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RoleClassification:
    """Result of a Tier 2 role classification call."""

    role: str  # "citizen", "civil_servant", "public_official"
    should_redact: bool
    confidence: float
    reason_nl: str


@dataclass
class ContentAnnotation:
    """A single annotation from Tier 3 content analysis."""

    woo_article: str
    label_nl: str  # qualitative label, e.g. "Mogelijk persoonlijke beleidsopvatting"
    analysis_nl: str  # explanation of why flagged
    likelihood: str  # "high", "medium", "low"


@dataclass
class SentenceClassification:
    """Fact-vs-opinion classification for a single sentence (art. 5.2)."""

    sentence: str
    classification: str  # "fact", "opinion", "prognosis", "policy_alternative", "mixed"
    explanation_nl: str


@dataclass
class ContentAnalysisResult:
    """Result of a Tier 3 content analysis call."""

    annotations: list[ContentAnnotation] = field(default_factory=list)
    sentence_classifications: list[SentenceClassification] = field(default_factory=list)
    summary_nl: str = ""


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def classify_role(
        self,
        person_name: str,
        surrounding_context: str,
        document_type: str | None = None,
    ) -> RoleClassification:
        """Tier 2: classify whether a detected person is a citizen, civil servant,
        or public official acting in capacity."""

    @abstractmethod
    async def analyze_content(
        self,
        passage: str,
        document_type: str | None = None,
        surrounding_context: str | None = None,
    ) -> ContentAnalysisResult:
        """Tier 3: analyze a passage for potential redaction grounds."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable and ready."""
