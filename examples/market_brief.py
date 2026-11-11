"""Proof call: the market brief ($0.01) through the LangChain tool.

Run with a funded wallet:
    AGENT_PRIVATE_KEY=0x... python examples/market_brief.py

Prints the brief data and the settlement proof (Base transaction hash).
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
    brief = next(t for t in tools if t.name == "blockchain_iq_brief")
    result = json.loads(brief.invoke({}))
    if "error" in result:
        print("Call failed:", result)
        raise SystemExit(1)
    print("Brief asOf:", result["data"].get("asOf"))
    print("Coins:", [(c["symbol"], c["price"]) for c in result["data"].get("coins", [])])
    print("Settlement proof:", json.dumps(result.get("_payment"), indent=2))
    print("Tx (Base): https://basescan.org/tx/" + result["_payment"]["transaction"])


if __name__ == "__main__":
    main()
