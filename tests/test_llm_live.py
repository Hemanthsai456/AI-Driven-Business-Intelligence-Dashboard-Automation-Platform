import os
import pytest
from orchestrator.llm import GeminiClient, GroqClient, OllamaClient, get_strict_json_schema
from orchestrator.schemas import CandidatePlan

# Opt-in live smoke test per provider
RUN_LIVE_TESTS = os.getenv("RUN_LIVE_TESTS") == "1"

@pytest.mark.skipif(not RUN_LIVE_TESTS, reason="Live tests are disabled. Set RUN_LIVE_TESTS=1 to enable.")
class TestLLMLive:
    def setup_method(self):
        self.prompt = "Generate a dummy plan for dataset 'test_ds' where intent is 'Show total sales by month'. Metric column is 'sales', dimension column is 'date' with MONTH granularity."
        self.schema = get_strict_json_schema(CandidatePlan)

    def test_gemini_live(self):
        client = GeminiClient()
        plan, log = client.generate_structured(self.prompt, self.schema)
        assert isinstance(plan, dict) or isinstance(plan, list)
        assert log.latency_seconds > 0

    def test_groq_live(self):
        client = GroqClient()
        plan, log = client.generate_structured(self.prompt, self.schema)
        assert isinstance(plan, dict) or isinstance(plan, list)
        assert log.latency_seconds > 0

    def test_ollama_live(self):
        client = OllamaClient()
        plan, log = client.generate_structured(self.prompt, self.schema)
        assert isinstance(plan, dict) or isinstance(plan, list)
        assert log.latency_seconds > 0
