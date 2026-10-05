"""Provider configuration constants and environment variable keys."""

import os

PROVIDER_ENV: str = "PROVIDER"
DEFAULT_PROVIDER: str = "gemini"

GEMINI_MODEL_ENV: str = "GEMINI_MODEL"
DEFAULT_GEMINI_MODEL: str = "gemini-3.8-flash"
GEMINI_API_KEY_ENV: str = "GEMINI_API_KEY"

GROQ_MODEL_ENV: str = "GROQ_MODEL"
DEFAULT_GROQ_MODEL: str = "openai/gpt-oss-20b"
GROQ_API_KEY_ENV: str = "GROQ_API_KEY"

OLLAMA_MODEL_ENV: str = "OLLAMA_MODEL"
DEFAULT_OLLAMA_MODEL: str = "llama3"
OLLAMA_BASE_URL_ENV: str = "OLLAMA_BASE_URL"
DEFAULT_OLLAMA_BASE_URL: str = "http://localhost:11434"

ACTIVE_PROVIDERS_ENV: str = "ACTIVE_PROVIDERS"
DEFAULT_ACTIVE_PROVIDERS: str = "gemini,groq,ollama,rule_based_baseline"
