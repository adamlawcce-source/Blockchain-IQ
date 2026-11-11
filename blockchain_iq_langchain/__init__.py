"""LangChain tools for the Blockchain IQ x402 API.

Pay-per-call crypto data and research, settled in USDC on Base through the
open x402 standard. No account, no API key — a wallet holding a little USDC
is the only credential.

Quick start::

    from blockchain_iq_langchain import make_tools

    tools = make_tools()  # reads AGENT_PRIVATE_KEY for paid calls
    brief_tool = next(t for t in tools if t.name == "blockchain_iq_brief")
    print(brief_tool.invoke({}))  # $0.01, returns JSON + settlement proof
"""

from __future__ import annotations

from .client import (
    BlockchainIQClient,
    PaymentFailedError,
    PaymentRequiredError,
    list_resources,
)
from .resources import BY_ID, RESOURCES
from .tools import make_tool, make_tools

__version__ = "0.1.0"

__all__ = [
    "BlockchainIQClient",
    "PaymentFailedError",
    "PaymentRequiredError",
    "list_resources",
    "make_tool",
    "make_tools",
    "BY_ID",
    "RESOURCES",
    "__version__",
]
