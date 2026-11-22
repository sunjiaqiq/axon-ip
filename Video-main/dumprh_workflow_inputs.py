import asyncio
import os
from typing import Any

from comfykit.comfyui.runninghub_client import RunningHubClient


WORKFLOW_ID = "2037049003786903554"


def _summarize_value(v: Any) -> str:
    if isinstance(v, list):
        if not v:
            return "list(len=0) []"
        return f"list(len={len(v)}) first={repr(v[0])}"
    return f"{repr(v)} (type={type(v).__name__})"


async def main() -> None:
    api_key = os.getenv("RUNNINGHUB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RUNNINGHUB_API_KEY env var is required")

    client = RunningHubClient(api_key=api_key, base_url="https://www.runninghub.cn")
    try:
        wf = await client.get_workflow_json(WORKFLOW_ID)
        print(f"workflowId={WORKFLOW_ID}, nodes={list(wf.keys())}")

        for nid, nd in wf.items():
            print(f"\nNODE {nid} class_type={nd.get('class_type')}")
            inputs = nd.get("inputs") or {}
            if not inputs:
                print("  (no inputs)")
                continue

            for k, v in inputs.items():
                print(f"  input {k}: {_summarize_value(v)}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

