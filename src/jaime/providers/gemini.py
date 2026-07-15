"""Gemini AI provider using the REST API directly (stdlib only)."""

import json
import logging
import traceback
import urllib.request
import urllib.error

from jaime.providers.base import AIProvider

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(AIProvider):
    def __init__(self, api_token: str, model: str = "gemini-2.0-flash"):
        self._api_token = api_token
        self._model = model

    def check(self) -> str | None:
        """Lightweight connectivity check via model list endpoint."""
        url = f"{GEMINI_API_BASE}?key={self._api_token}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            return None
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            logger.warning("Gemini check failed:\n%s", traceback.format_exc())
            return f"Gemini API HTTP {e.code}: {body}"
        except Exception as e:
            logger.warning("Gemini check failed:\n%s", traceback.format_exc())
            return f"Gemini connection error: {e}"

    def generate(self, prompt: str) -> str:
        url = f"{GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_token}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
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

        return parts[0].get("text", "")
