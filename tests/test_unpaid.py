"""Live test: the unpaid flow returns HTTP 402 with the price (no key, no payment).

Hits the real Blockchain IQ API. Nothing is signed and nothing is paid.
"""

import base64
import json

import pytest
import requests

from blockchain_iq_langchain import BlockchainIQClient, PaymentRequiredError

BASE = "https://www.blockchainiq.co/api/x402/v1"


def test_catalogue_is_free_and_lists_brief():
    client = BlockchainIQClient()
    catalogue = client.get_catalogue()
    assert catalogue["x402Version"] == 2
    assert catalogue["network"] == "eip155:8453"
    brief = next(r for r in catalogue["data"] if r["id"] == "brief")
    assert brief["price"] == "$0.01"


def test_brief_without_key_raises_payment_required_with_price():
    client = BlockchainIQClient()
    with pytest.raises(PaymentRequiredError) as excinfo:
        client.get_brief()
    assert excinfo.value.price_usd == 0.01
    assert excinfo.value.resource_id == "brief"


def test_raw_402_header_names_the_price_and_payee():
    resp = requests.get(BASE + "/brief", timeout=60)
    assert resp.status_code == 402
    raw = resp.headers["PAYMENT-REQUIRED"]
    raw += "=" * (-len(raw) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(raw))
    accept = next(a for a in decoded["accepts"] if a["network"] == "eip155:8453")
    assert accept["scheme"] == "exact"
    assert accept["amount"] == "10000"  # $0.01, USDC has 6 decimals
    assert accept["asset"] == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    assert accept["payTo"] == "0x617dA9383fbA67e86137BC4924b8b7E400fB7C9e"
    assert decoded["x402Version"] == 2
