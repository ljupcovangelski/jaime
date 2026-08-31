"""Gemini AI provider using the REST API directly (stdlib only)."""

import json
import logging
import traceback
import urllib.error
import urllib.request

from jaime.incident import UsageMetadata
from jaime.providers.base import AIProvider

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_ERROR_BODY_MAX = 500


class GeminiProvider(AIProvider):
    def __init__(self, api_token: str, model: str = "gemini-2.0-flash"):
        self._api_token = api_token
        self._model = model

    def check(self) -> str | None:
        """Lightweight connectivity check via model list endpoint."""
        # Token passed as a header to avoid exposure in URLs and proxy logs.
        url = GEMINI_API_BASE
        req = urllib.request.Request(
            url,
            headers={"x-goog-api-key": self._api_token},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            return None
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:_ERROR_BODY_MAX]
            logger.warning("Gemini check failed:\n%s", traceback.format_exc())
            return f"Gemini API HTTP {e.code}: {body}"
        except Exception as e:
            logger.warning("Gemini check failed:\n%s", traceback.format_exc())
            return f"Gemini connection error: {e}"

    def generate(self, prompt: str) -> tuple[str, UsageMetadata]:
        url = f"{GEMINI_API_BASE}/{self._model}:generateContent"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_token,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:_ERROR_BODY_MAX]
            logger.error("Gemini API HTTP %s: %s", e.code, body)
            raise
        except urllib.error.URLError as e:
            logger.error("Gemini API connection error: %s", e.reason)
            raise

        candidates = result.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {result}")

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError(f"Gemini response has no parts: {candidates[0]}")

        text = parts[0].get("text", "")

        # Extract token usage from usageMetadata if present.
        raw_usage = result.get("usageMetadata", {})
        usage = UsageMetadata(
            prompt_tokens=raw_usage.get("promptTokenCount", 0),
            completion_tokens=raw_usage.get("candidatesTokenCount", 0),
            total_tokens=raw_usage.get("totalTokenCount", 0),
            cost_usd=None,  # Gemini does not report cost in the response.
            model=self._model,
        )

        return text, usage
