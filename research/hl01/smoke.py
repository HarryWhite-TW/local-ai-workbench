"""One natural input, bounded requests, and a shareable receipt with no HTTP bodies."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from subscription import EFFORT, SLUG, build_model
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from work_index import WorkIndex


async def main():
    run = str(uuid.uuid4())
    output = Path(__file__).parent / "runs" / f"smoke-{run}.json"
    output.parent.mkdir(exist_ok=True)
    record = {"attempt_id": run, "utc": datetime.now(timezone.utc).isoformat(),
              "input": "我們以前做過哪些工作？", "requested_model": SLUG,
              "requested_effort": EFFORT, "wire": [], "tools": []}
    client = None
    try:
        model, client = build_model(record["wire"])
        index = WorkIndex()
        agent = Agent(model, instructions="你是工程工作助理。依可查證的資料回答，附上來源。", retries=0,
                      model_settings={"openai_reasoning_effort": EFFORT})

        @agent.tool_plain
        def search_works(query: str = "") -> list[dict]:
            """Search permitted work summaries by name or list them in date order."""
            found = index.search(query)
            record["tools"].append({"tool": "search_works", "query": query, "result": found})
            return found

        async with asyncio.timeout(100):
            result = await agent.run(record["input"], usage_limits=UsageLimits(request_limit=3))
        record.update(status="RESPONDED", run_id=result.run_id, output=result.output,
                      response_model=result.response.model_name)
    except Exception as error:
        record.update(status="BLOCKED", error=type(error).__name__,
                      http_status=getattr(error, "status_code", None))
        # Omit raw bodies, headers, exception text and authentication data.
        cause = error
        chain = []
        while cause is not None and type(cause).__name__ not in chain:
            chain.append(type(cause).__name__)
            cause = cause.__cause__ or cause.__context__
        record["error_chain"] = chain
    finally:
        if client is not None:
            await client.aclose()
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.name, record["status"])
    return int(record["status"] != "RESPONDED")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
