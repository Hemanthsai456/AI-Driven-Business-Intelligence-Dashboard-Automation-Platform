"""Intent Classifier and Dispatch Router for Dataset Chat (Step 8 / Roadmap #7).

Identifies the primary user intent:
1. Unsupported forecasting / projection
2. Causal inference claims
3. Dataset understanding & metadata queries
4. Pre-computed Evidence-Grounded Insight queries
5. Dashboard panel / visual provenance queries
6. Follow-up / pronoun / context-shift queries
7. Direct or grouped analytical queries
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.chat.schemas import ChatIntentType, ConversationContext


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b[a-z0-9_]+\b", text.lower()))


class ChatIntentClassifier:
    """Classifies user chat messages into domain-aware intent types."""

    # Unsupported forecasting keywords
    FORECAST_PATTERNS = [
        r"\bpredict\b",
        r"\bforecast\b",
        r"\bfuture\b",
        r"\bwill\s+(?:increase|decrease|grow|drop|fall|change|be)\b",
        r"\bprojection\b",
        r"\bprojected\b",
        r"\bnext\s+(?:year|month|quarter|week|decade)\b",
        r"\bextrapolate\b",
        r"\bexpected\s+(?:revenue|sales|stay|marks|temperature)\b",
    ]

    # Causal inference patterns
    CAUSAL_PATTERNS = [
        r"\bwhy\s+did\s+.+\s+cause\b",
        r"\bprove\s+that\s+.+\s+caused\b",
        r"\bis\s+.+\s+the\s+cause\s+of\b",
        r"\bdoes\s+.+\s+cause\b",
        r"\bcausation\b",
        r"\bcausality\b",
        r"\bcaused\s+by\b",
        r"\bresponsible\s+for\s+causing\b",
    ]

    # Dataset metadata & structure questions
    METADATA_PATTERNS = [
        r"\bwhat\s+(?:columns|fields|variables)\b",
        r"\bwhich\s+(?:columns|fields|variables)\b",
        r"\bwhat\s+(?:columns|fields|variables)\s+(?:are\s+available|exist|do\s+we\s+have|are\s+in\s+this\s+dataset)\b",
        r"\bwhat\s+does\s+this\s+dataset\s+contain\b",
        r"\btell\s+me\s+about\s+this\s+dataset\b",
        r"\bwhat\s+(?:metrics|measures)\s+can\s+i\s+analyze\b",
        r"\bwhat\s+dimensions\s+can\s+i\s+use\b",
        r"\bhow\s+many\s+(?:rows|records|columns|entries|lines)\b",
        r"\bdataset\s+(?:overview|summary|info|profile|structure|metadata|schema)\b",
        r"\bwhat\s+are\s+the\s+data\s+types\b",
        r"\bshow\s+(?:columns|schema|metadata|data\s+types|fields)\b",
        r"\bmissing\s+values\b",
        r"\bdescribe\s+(?:the\s+)?dataset\b",
    ]

    # Insight-specific queries
    INSIGHT_PATTERNS = [
        r"\bwhat\s+are\s+the\s+(?:most\s+important|key|top|main)\s+(?:findings|insights|takeaways)\b",
        r"\bshow\s+(?:me\s+)?(?:the\s+)?(?:key\s+)?insights\b",
        r"\bwhy\s+is\s+this\s+insight\s+(?:important|significant|useful)\b",
        r"\bwhich\s+insight\s+has\s+the\s+strongest\s+evidence\b",
        r"\bshow\s+(?:me\s+)?(?:the\s+)?evidence\s+for\s+(?:that|this)\s+insight\b",
        r"\bsummarize\s+(?:the\s+)?findings\b",
        r"\bimportant\s+things\s+in\s+this\s+dataset\b",
        r"\bdiscover\s+insights\b",
    ]

    # Dashboard-specific queries
    DASHBOARD_PATTERNS = [
        r"\bwhy\s+is\s+this\s+chart\s+(?:here|chosen|selected)\b",
        r"\bwhy\s+did\s+you\s+choose\s+(?:this\s+chart|that\s+visual|average\s+\w+)\b",
        r"\bhow\s+was\s+this\s+(?:kpi|hero\s+chart|tile)\s+calculated\b",
        r"\bshow\s+(?:me\s+)?(?:the\s+)?sql\s+for\s+this\s+(?:chart|tile|dashboard|hero)\b",
        r"\bwhat\s+evidence\s+supports\s+this\s+(?:chart|tile|dashboard)\b",
        r"\bdashboard\s+explanation\b",
    ]

    # Direct provenance / calculation of previous result
    PROVENANCE_PATTERNS = [
        r"\bhow\s+(?:was|did\s+you\s+calculate)\s+(?:that|this|the\s+result|the\s+number)\b",
        r"\bhow\s+did\s+you\s+get\s+(?:that|this|that\s+number)\b",
        r"\bshow\s+(?:me\s+)?(?:the\s+)?sql\b",
        r"\bwhat\s+was\s+the\s+sql\s+query\b",
        r"\bwhat\s+is\s+the\s+sql\b",
        r"\bshow\s+(?:me\s+)?(?:the\s+)?query\b",
        r"\bshow\s+provenance\b",
    ]

    # Follow-up indicators (requiring context from previous turn)
    FOLLOWUP_INDICATORS = [
        r"^(?:which\s+one|which)\s+(?:is|was)\s+(?:the\s+)?(?:highest|lowest|best|worst|top|bottom|maximum|minimum)",
        r"^(?:who|which)\s+(?:made|had|recorded|has|got)\s+the\s+(?:most|least|highest|lowest)",
        r"^show\s+(?:me\s+)?(?:the\s+)?(?:top|bottom)\s+\d+",
        r"^what\s+about\s+(?:in\s+|for\s+)?",
        r"^how\s+about\s+",
        r"^and\s+(?:for\s+|in\s+)?",
        r"^now\s+(?:by|for|in)\s+",
        r"^break\s+(?:it\s+)?down\s+by\s+",
        r"\bit\b",
        r"\bthat\b",
        r"\bthose\b",
        r"\bthem\b",
    ]

    def classify_intent(
        self,
        message: str,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
        context: Optional[ConversationContext] = None,
    ) -> Tuple[ChatIntentType, Optional[str]]:
        """Classify user query into appropriate ChatIntentType.

        Returns:
            (ChatIntentType, explanation_or_notice)
        """
        msg_clean = (message or "").strip().lower()
        if not msg_clean:
            return ChatIntentType.GENERAL_HELP, "Empty message received."

        # 1. Check for Unsupported Forecasting
        for pat in self.FORECAST_PATTERNS:
            if re.search(pat, msg_clean):
                return (
                    ChatIntentType.UNSUPPORTED_OR_CAUSAL,
                    "I can analyze historical patterns and current relationships in this dataset, but I do not currently perform future forecasting or predictive modeling.",
                )

        # 2. Check for Causal Questions
        for pat in self.CAUSAL_PATTERNS:
            if re.search(pat, msg_clean):
                return (
                    ChatIntentType.UNSUPPORTED_OR_CAUSAL,
                    "The dataset shows observational correlations and statistical associations, but this analysis does not establish causal mechanisms.",
                )

        # 3. Check for Provenance / SQL on previous result
        for pat in self.PROVENANCE_PATTERNS:
            if re.search(pat, msg_clean):
                if context and context.last_compiled_sql:
                    return ChatIntentType.PROVENANCE_OR_SQL, None
                return ChatIntentType.PROVENANCE_OR_SQL, "No previous query found in current session."

        # 4. Check for Dataset Metadata / Understanding
        for pat in self.METADATA_PATTERNS:
            if re.search(pat, msg_clean):
                return ChatIntentType.DATASET_METADATA, None

        # 5. Check for Insight Questions
        for pat in self.INSIGHT_PATTERNS:
            if re.search(pat, msg_clean):
                return ChatIntentType.INSIGHT_EXPLANATION, None

        # 6. Check for Dashboard Explanation Questions
        for pat in self.DASHBOARD_PATTERNS:
            if re.search(pat, msg_clean):
                return ChatIntentType.DASHBOARD_EXPLANATION, None

        # 7. Check for Comparison Queries
        if re.search(r"\bcompare\b", msg_clean):
            return ChatIntentType.COMPARISON, None

        # 8. Check for Follow-up / Context-dependent Questions
        if context and context.last_question and (context.last_metric or context.last_dimensions):
            for pat in self.FOLLOWUP_INDICATORS:
                if re.search(pat, msg_clean):
                    return ChatIntentType.FOLLOW_UP, None

        # 9. Default to standard Analytical Query
        return ChatIntentType.ANALYTICAL_QUERY, None
