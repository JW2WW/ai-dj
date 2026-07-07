"""Swappable LLM client: Gemini primary, Groq fallback.

Exposes a single method, ``generate(prompt) -> str``. If the primary provider
errors or rate-limits, it automatically falls back to the secondary provider so
the DJ is never fully blocked when one free tier tightens.
"""
import os

from dotenv import load_dotenv

from paths import EXE_DIR

load_dotenv(EXE_DIR / ".env")

# Free-tier friendly defaults; override via env or config.yaml.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class LLMError(Exception):
    """Raised when every configured provider fails."""


class LLMClient:
    def __init__(
        self,
        primary: str = "gemini",
        fallback: str | None = "groq",
        gemini_model: str | None = None,
        groq_model: str | None = None,
    ):
        self.primary = primary
        self.fallback = fallback
        self.gemini_model = gemini_model or GEMINI_MODEL
        self.groq_model = groq_model or GROQ_MODEL
        self._gemini = None
        self._groq = None

    def _gemini_client(self):
        if self._gemini is None:
            from google import genai

            key = os.getenv("GEMINI_API_KEY")
            if not key:
                raise LLMError("GEMINI_API_KEY not set")
            self._gemini = genai.Client(api_key=key)
        return self._gemini

    def _groq_client(self):
        if self._groq is None:
            from groq import Groq

            key = os.getenv("GROQ_API_KEY")
            if not key:
                raise LLMError("GROQ_API_KEY not set")
            self._groq = Groq(api_key=key)
        return self._groq

    def _call_gemini(self, prompt: str, max_tokens: int) -> str:
        from google.genai import types

        client = self._gemini_client()
        resp = client.models.generate_content(
            model=self.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (resp.text or "").strip()
        if not text:
            raise LLMError("Gemini returned empty response")
        return text

    def _call_groq(self, prompt: str, max_tokens: int) -> str:
        client = self._groq_client()
        resp = client.chat.completions.create(
            model=self.groq_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise LLMError("Groq returned empty response")
        return text

    def _call(self, provider: str, prompt: str, max_tokens: int) -> str:
        if provider == "gemini":
            return self._call_gemini(prompt, max_tokens)
        if provider == "groq":
            return self._call_groq(prompt, max_tokens)
        raise LLMError(f"Unknown provider: {provider}")

    def generate(self, prompt: str, max_tokens: int = 150) -> str:
        providers = [self.primary] + ([self.fallback] if self.fallback else [])
        errors: list[str] = []
        for provider in providers:
            try:
                return self._call(provider, prompt, max_tokens)
            except Exception as e:
                errors.append(f"{provider}: {e}")
        raise LLMError("All providers failed -> " + " | ".join(errors))


def get_llm_client() -> LLMClient:
    """Build an LLM client from config.yaml (with env overrides)."""
    from config import get_config

    cfg = get_config()
    llm_cfg = cfg["llm"]
    return LLMClient(
        primary=llm_cfg.get("primary", "gemini"),
        fallback=llm_cfg.get("fallback", "groq"),
        gemini_model=llm_cfg.get("gemini_model"),
        groq_model=llm_cfg.get("groq_model"),
    )


if __name__ == "__main__":
    client = get_llm_client()
    out = client.generate(
        "In one punchy sentence, introduce the song 'The Gambler' by Kenny "
        "Rogers as a radio DJ would.",
        max_tokens=80,
    )
    print(out)
