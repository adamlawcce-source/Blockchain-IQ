"""Paid-call client for the Blockchain IQ x402 API.

Implements the exact flow from https://www.blockchainiq.co/blog/pay-per-call-crypto-data-x402
and https://www.blockchainiq.co/agents (x402 protocol v2, USDC on Base):

1. Plain GET, no headers.
2. HTTP 402 with a ``PAYMENT-REQUIRED`` header (base64 JSON: price, asset,
   network, pay-to address).
3. The official ``x402`` Python SDK signs a USDC EIP-3009 authorization
   locally and the request is retried with a ``PAYMENT-SIGNATURE`` header.
4. HTTP 200 with the data, plus a ``PAYMENT-RESPONSE`` header carrying the
   settlement transaction hash. A 404 or an error is never charged.

The private key is only ever read from the ``AGENT_PRIVATE_KEY`` environment
variable (or passed explicitly to :class:`BlockchainIQClient`); it is never
logged, printed or stored. Settlement is gasless for the payer.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from .resources import BASE_URL, BY_ID, CATALOGUE_URL, NETWORK, RESOURCES

#: Default spend cap per call, in US dollars. The dearest catalogue resource
#: is $2.00; the bounty proof calls (brief $0.01, event-risk $0.05) are far
#: below this. Raise it explicitly if you need the expensive resources.
DEFAULT_MAX_USD_PER_CALL = 0.10


class PaymentRequiredError(Exception):
    """Raised when a paid resource is requested without a funded signer.

    Carries the price so the caller can decide whether to pay. No payment
    is attempted.
    """

    def __init__(self, resource_id: str, price_usd: float, url: str) -> None:
        self.resource_id = resource_id
        self.price_usd = price_usd
        self.url = url
        super().__init__(
            f"Payment required for '{resource_id}': ${price_usd:.2f} in USDC on Base. "
            f"Pass a private key (AGENT_PRIVATE_KEY) holding at least "
            f"${price_usd:.2f} USDC on Base to pay for {url}."
        )


class PaymentFailedError(Exception):
    """Raised when the paid retry does not return HTTP 200."""


def _decode_payment_response(header_value: str | None) -> dict[str, Any] | None:
    """Decode the PAYMENT-RESPONSE header into the settlement proof."""
    if not header_value:
        return None
    try:
        from x402.http import decode_payment_response_header

        settled = decode_payment_response_header(header_value)
        return {
            "success": settled.success,
            "payer": settled.payer,
            "transaction": settled.transaction,
            "network": settled.network,
            "amount_atomic": settled.amount,
        }
    except Exception:
        return {"raw": header_value}


class BlockchainIQClient:
    """Minimal client for the Blockchain IQ x402 API.

    Args:
        private_key: Hex EVM private key (with or without ``0x``) of a wallet
            holding USDC on Base. Read from ``AGENT_PRIVATE_KEY`` when omitted.
            ``None`` means read-only: free resources work, paid ones raise
            :class:`PaymentRequiredError` with the price instead of paying.
        max_usd_per_call: Spend control — refuse any single payment above
            this amount in dollars, whatever the server asks for.
        session: Optional :class:`requests.Session` (a fresh one is created
            otherwise).
    """

    def __init__(
        self,
        private_key: str | None = None,
        max_usd_per_call: float = DEFAULT_MAX_USD_PER_CALL,
        session: requests.Session | None = None,
    ) -> None:
        self.private_key = private_key or os.environ.get("AGENT_PRIVATE_KEY")
        self.max_usd_per_call = max_usd_per_call
        self.session = session or requests.Session()
        self._http_client = None  # built lazily, only when paying
        self._account_address: str | None = None

    @property
    def account_address(self) -> str | None:
        """The payer address derived from the private key, or ``None``."""
        if self._account_address is None and self.private_key:
            from eth_account import Account

            self._account_address = Account.from_key(self.private_key).address
        return self._account_address

    # -- x402 plumbing -----------------------------------------------------

    def _build_http_client(self):
        """Build the official x402 SDK client (only when a payment is due)."""
        if self._http_client is not None:
            return self._http_client
        from eth_account import Account
        from x402 import SchemeRegistration, x402ClientConfig, x402ClientSync
        from x402.http import x402HTTPClientSync
        from x402.mechanisms.evm.exact.client import ExactEvmScheme

        account = Account.from_key(self.private_key)
        self._account_address = account.address
        client = x402ClientSync.from_config(
            x402ClientConfig(
                schemes=[
                    SchemeRegistration(
                        network=NETWORK, client=ExactEvmScheme(account)
                    )
                ],
                spend_controls={
                    "max_amount_per_payment": self.max_usd_per_call
                },
            )
        )
        self._http_client = x402HTTPClientSync(client)
        return self._http_client

    def _paid_get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET a paid URL, paying the 402 with the configured wallet."""
        if not self.private_key:
            raise PaymentRequiredError("<unknown>", 0.0, url)
        http_client = self._build_http_client()
        resp = self.session.get(url, params=params, timeout=60)
        payment: dict[str, Any] | None = None
        if resp.status_code == 402:
            payment_headers, _payload = http_client.handle_402_response(
                dict(resp.headers), resp.content, url
            )
            resp = self.session.get(
                url, params=params, headers=payment_headers, timeout=60
            )
            payment = _decode_payment_response(
                resp.headers.get("payment-response")
                or resp.headers.get("PAYMENT-RESPONSE")
            )
        if resp.status_code != 200:
            raise PaymentFailedError(
                f"Paid call to {url} failed with HTTP {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        body = resp.json()
        body["_payment"] = payment
        return body

    # -- public API ---------------------------------------------------------

    def get_catalogue(self) -> dict[str, Any]:
        """The free catalogue: every resource, price and response shape."""
        return self.session.get(CATALOGUE_URL, timeout=60).json()

    def get_sample(self) -> dict[str, Any]:
        """The free sample (Bitcoin network activity for its latest day)."""
        return self.session.get(BASE_URL + "/api/x402/v1/sample", timeout=60).json()

    def get_resource(self, resource_id: str, **params: Any) -> dict[str, Any]:
        """Call one catalogue resource by id.

        Path parameters (``{slug}``, ``{chain}`` ...) are passed as keyword
        arguments; the rest become query parameters. Returns the JSON body;
        paid calls also carry a ``_payment`` key with the settlement proof
        (transaction hash, payer, network, amount in atomic USDC units).
        """
        resource = BY_ID[resource_id]
        path = resource["path"]
        query: dict[str, Any] = {}
        for name, value in params.items():
            placeholder = "{" + name + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(value))
            else:
                query[name] = value
        if "{" in path:
            missing = [p for p in path.split("{")[1:]]
            raise ValueError(f"Missing path parameter(s) for {resource_id}: {missing}")
        url = BASE_URL + path
        price_usd = resource["price_usd"]
        if price_usd is None:
            resp = self.session.get(url, params=query or None, timeout=60)
            if resp.status_code != 200:
                raise PaymentFailedError(
                    f"Call to {url} failed with HTTP {resp.status_code}: "
                    f"{resp.text[:500]}"
                )
            body = resp.json()
            body["_payment"] = None
            return body
        if not self.private_key:
            raise PaymentRequiredError(resource_id, price_usd, url)
        return self._paid_get(url, params=query or None)

    # Convenience wrappers for the two bounty-qualifying resources.

    def get_brief(self) -> dict[str, Any]:
        """Market brief: majors, next-48h events, risk flags. $0.01/call."""
        return self.get_resource("brief")

    def get_event_risk(self, days: int = 7, min_importance: int = 1) -> dict[str, Any]:
        """Scheduled market-moving events. $0.05/call."""
        return self.get_resource(
            "event-risk", days=days, minImportance=min_importance
        )


def list_resources() -> list[dict[str, Any]]:
    """All catalogue resources (id, path, price, description, params)."""
    return RESOURCES


__all__ = [
    "BlockchainIQClient",
    "PaymentFailedError",
    "PaymentRequiredError",
    "DEFAULT_MAX_USD_PER_CALL",
    "list_resources",
]
