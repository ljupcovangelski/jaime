"""OpenRouter AI provider using the REST API directly (stdlib only)."""

import json
import logging
import urllib.request
import urllib.error

from jaime.providers.base import AIProvider

logger = logging.getLogger(__name__)

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(AIProvider):
    def __init__(self, api_token: str, model: str = "anthropic/claude-sonnet-4"):
        self._api_token = api_token
        self._model = model

    def generate(self, prompt: str) -> str:
        url = f"{OPENROUTER_API_BASE}/chat/completions"
        payload = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_token}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            logger.error("OpenRouter API HTTP %s: %s", e.code, body)
            raise
        except urllib.error.URLError as e:
            logger.error("OpenRouter API connection error: %s", e.reason)
            raise

        choices = result.get("choices", [])
        if not choices:
            raise RuntimeError(f"OpenRouter returned no choices: {result}")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        return content
