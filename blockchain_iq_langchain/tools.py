"""LangChain tools for the Blockchain IQ x402 API.

One tool per catalogue resource, built from :mod:`blockchain_iq_langchain.resources`
(which mirrors the live catalogue). Free resources work with no wallet; paid
resources settle in USDC on Base through x402 v2 and need a private key — see
:meth:`make_tools`.

Example (LangChain agent)::

    from blockchain_iq_langchain import make_tools

    tools = make_tools()  # reads AGENT_PRIVATE_KEY for paid calls
    # brief = $0.01/call, event-risk = $0.05/call
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from .client import BlockchainIQClient, PaymentFailedError, PaymentRequiredError
from .resources import BY_ID, RESOURCES

_PATH_PARAM = re.compile(r"\{(\w+)\}")


def _args_schema(resource: dict[str, Any]) -> type[BaseModel]:
    """Build a Pydantic args model from a resource's parameters.

    Path parameters (``{slug}`` in the path) are required; query parameters
    are optional.
    """
    path_params = _PATH_PARAM.findall(resource["path"])
    fields: dict[str, Any] = {}
    for name in path_params:
        desc = (resource["params"].get(name) or f"Path parameter {name}.")
        fields[name] = (str, Field(description=desc))
    for name, desc in resource["params"].items():
        if name in path_params:
            continue
        fields[name] = (str | None, Field(default=None, description=desc or name))
    model = create_model(
        f"{resource['id'].title().replace('-', '')}Args",
        **fields,  # type: ignore[arg-type]
    )
    return model


def _tool_description(resource: dict[str, Any]) -> str:
    price = resource["price"]
    paid_note = (
        f"Paid: {price} per call in USDC on Base (x402). "
        if price != "free"
        else "Free: no payment, no wallet needed. "
    )
    return (
        f"{resource['title']}. {resource['description']} {paid_note}"
        f"Returns JSON. Paid calls also include the settlement proof "
        f"(transaction hash) under `_payment`."
    )


def make_tool(
    resource_id: str,
    client: BlockchainIQClient | None = None,
    *,
    private_key: str | None = None,
    max_usd_per_call: float = 0.10,
) -> StructuredTool:
    """Build the LangChain tool for one catalogue resource."""
    resource = BY_ID[resource_id]
    client = client or BlockchainIQClient(
        private_key=private_key, max_usd_per_call=max_usd_per_call
    )
    schema = _args_schema(resource)

    def _run(**kwargs: Any) -> str:
        try:
            result = client.get_resource(resource_id, **kwargs)
        except PaymentRequiredError as exc:
            return json.dumps(
                {
                    "error": "payment_required",
                    "resource": resource_id,
                    "price_usd": exc.price_usd,
                    "message": str(exc),
                }
            )
        except PaymentFailedError as exc:
            return json.dumps({"error": "payment_failed", "resource": resource_id, "message": str(exc)})
        return json.dumps(result)

    return StructuredTool.from_function(
        func=_run,
        name="blockchain_iq_" + resource_id.replace("-", "_"),
        description=_tool_description(resource),
        args_schema=schema,
    )


def make_tools(
    client: BlockchainIQClient | None = None,
    *,
    private_key: str | None = None,
    max_usd_per_call: float = 0.10,
    paid_only: bool = False,
) -> list[StructuredTool]:
    """Build LangChain tools for every Blockchain IQ catalogue resource.

    Args:
        client: A configured :class:`BlockchainIQClient` (created from
            ``private_key``/``max_usd_per_call`` when omitted).
        private_key: Hex EVM private key of a wallet holding USDC on Base,
            or ``None`` to read ``AGENT_PRIVATE_KEY``. Without a key, free
            tools work and paid tools return a ``payment_required`` error
            naming the price instead of paying.
        max_usd_per_call: Spend control — refuse any single payment above
            this amount in dollars.
        paid_only: When true, only the paid resources are returned.
    """
    client = client or BlockchainIQClient(
        private_key=private_key, max_usd_per_call=max_usd_per_call
    )
    tools = []
    for resource in RESOURCES:
        if paid_only and resource["price_usd"] is None:
            continue
        tools.append(make_tool(resource["id"], client=client))
    return tools


__all__ = ["make_tool", "make_tools"]
