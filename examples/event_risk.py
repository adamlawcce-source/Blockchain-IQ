"""Proof call: event risk for the next 7 days ($0.05) through the LangChain tool.

Run with a funded wallet:
    AGENT_PRIVATE_KEY=0x... python examples/event_risk.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from blockchain_iq_langchain import make_tools


def main() -> None:
    if not os.environ.get("AGENT_PRIVATE_KEY"):
        print("Set AGENT_PRIVATE_KEY to a wallet holding USDC on Base.")
        raise SystemExit(1)
    tools = make_tools()
    event_risk = next(t for t in tools if t.name == "blockchain_iq_event_risk")
    result = json.loads(event_risk.invoke({"days": "7"}))
    if "error" in result:
        print("Call failed:", result)
        raise SystemExit(1)
    events = result["data"].get("events", result["data"])
    print("Events:", json.dumps(events, indent=2)[:2000])
    print("Settlement proof:", json.dumps(result.get("_payment"), indent=2))
    print("Tx (Base): https://basescan.org/tx/" + result["_payment"]["transaction"])


if __name__ == "__main__":
    main()
