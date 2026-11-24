"""Only the read-only Codex CLI credential adapter and the subscription responses endpoint."""
import os

os.environ["LOGFIRE_SEND_TO_LOGFIRE"] = "false"
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OPENAI_LOG"] = "error"

import httpx2
from pydantic_ai.models.openai_codex import OpenAICodexModel
from pydantic_ai.providers.openai_codex import OpenAICodexProvider


SLUG = "gpt-6.1-terra"
EFFORT = "medium"
ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"


def build_model(wire):
    async def check_destination(request):
        if request.method != "POST" or str(request.url) != ENDPOINT:
            raise RuntimeError("outside subscription inference scope")
        wire.append({"method": "POST", "destination": ENDPOINT})

    async def record_status(response):
        wire[-1]["status"] = response.status_code

    client = httpx2.AsyncClient(timeout=45, trust_env=False, follow_redirects=False,
                                event_hooks={"request": [check_destination], "response": [record_status]})
    provider = OpenAICodexProvider(http_client=client)
    provider.client.max_retries = 0
    return OpenAICodexModel(SLUG, provider=provider), client
