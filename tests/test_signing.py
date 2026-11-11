"""Offline test: the EIP-3009 signature round-trips.

Builds a real payment payload for the live /brief 402 requirements with a
throwaway key (never funded, never used on-chain), then recovers the signer
from the signature using the SDK's own typed-data builder. No network, no
funds — this proves the signing path the paid call relies on is correct.
"""

import json
import os

from eth_account import Account
from eth_account.messages import encode_typed_data

from x402.mechanisms.evm.eip712 import build_typed_data_for_signing
from x402.mechanisms.evm.exact.client import ExactEvmScheme
from x402.mechanisms.evm.types import ExactEIP3009Authorization
from x402.schemas import PaymentRequirements

EVIDENCE = os.path.join(
    os.path.dirname(__file__), "..", "..", "evidence", "payment-requirements-brief.json"
)


def test_eip3009_signature_recovers_to_signer():
    reqs = json.load(open(EVIDENCE))
    accept = next(a for a in reqs["accepts"] if a["network"] == "eip155:8453")
    requirements = PaymentRequirements(**accept)

    throwaway = Account.create()
    scheme = ExactEvmScheme(throwaway)
    payload = scheme.create_payment_payload(requirements)

    auth = payload["authorization"]
    assert auth["from"] == throwaway.address
    assert auth["to"] == accept["payTo"]
    assert auth["value"] == "10000"  # $0.01 in USDC atomic units
    assert auth["validAfter"] == "0"
    assert len(bytes.fromhex(auth["nonce"][2:])) == 32
    assert len(bytes.fromhex(payload["signature"][2:])) == 65

    # Rebuild the exact typed data the SDK signed and recover the signer.
    authorization = ExactEIP3009Authorization(
        from_address=auth["from"],
        to=auth["to"],
        value=auth["value"],
        valid_after=auth["validAfter"],
        valid_before=auth["validBefore"],
        nonce=auth["nonce"],
    )
    domain, types, primary_type, message = build_typed_data_for_signing(
        authorization,
        chain_id=8453,
        verifying_contract=accept["asset"],
        token_name=accept["extra"]["name"],
        token_version=accept["extra"]["version"],
    )
    signable = encode_typed_data(
        domain_data={
            "name": domain.name,
            "version": domain.version,
            "chainId": domain.chain_id,
            "verifyingContract": domain.verifying_contract,
        },
        # eth_account adds EIP712Domain itself; passing it explicitly
        # makes the primary type ambiguous.
        message_types={primary_type: types[primary_type]},
        message_data=message,
    )
    recovered = Account.recover_message(signable, signature=payload["signature"])
    assert recovered == throwaway.address
