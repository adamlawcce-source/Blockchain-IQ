# Blockchain IQ tools for LangChain

Pay-per-call crypto data and research for LangChain agents, settled in USDC
on Base through the open [x402](https://x402.org) standard. No account, no
API key — a wallet holding a little USDC is the only credential.

Built for the [Blockchain IQ x402 build bounties](https://www.blockchainiq.co/blog/x402-build-bounties):
one public repository with a working paid call through x402 to `brief`
($0.01) or `event-risk` ($0.05).

## Install

```bash
pip install -r requirements.txt
# or
pip install -e .
```

## Use

```python
from blockchain_iq_langchain import make_tools

tools = make_tools()  # reads AGENT_PRIVATE_KEY for paid calls
brief = next(t for t in tools if t.name == "blockchain_iq_brief")
print(brief.invoke({}))  # $0.01 — JSON plus the settlement proof
```

Every tool returns a JSON string. Paid calls include the settlement proof
under `_payment` (`transaction` = the Base tx hash, `payer`, `network`,
`amount_atomic` in USDC atomic units).

### Wallet

Set `AGENT_PRIVATE_KEY` to the hex EVM private key of a wallet holding USDC
on Base (a dedicated wallet with a small balance — never a main wallet).
Without a key, the free tools (`catalog`, `sample`, indexes) work and the
paid tools return a `payment_required` error naming the price instead of
paying. Spend control: any single payment above `max_usd_per_call`
(default $0.10) is refused, whatever the server asks for.

```python
tools = make_tools(max_usd_per_call=0.60)  # raise the cap if you need it
```

### With an agent

```python
from langchain.agents import create_agent
from blockchain_iq_langchain import make_tools

agent = create_agent("openai:gpt-4o", tools=make_tools())
agent.invoke({"messages": [{"role": "user", "content": "What's the market brief?"}]})
```

## What a call costs

| Resource | Price/call |
| --- | --- |
| Market brief (`brief`) | $0.01 |
| Event risk (`event-risk`) | $0.05 |
| x402 market, stablecoins, dispatches | $0.02 |
| Network activity, calendar, indices | $0.03 |
| Macro | $0.05 |
| Networks snapshot, Ripple Review | $0.10 |
| Dashboards | $0.03–$0.25 |
| Reports / research digests | $0.50 |
| Analyst pack | $2.00 |

The full list with descriptions is the free catalogue:
`GET https://www.blockchainiq.co/api/x402/v1` (also `/.well-known/x402`).

## How payment works

1. Plain `GET`, no headers.
2. HTTP 402 with a `PAYMENT-REQUIRED` header (base64 JSON: price, asset,
   network, pay-to address).
3. The official `x402` Python SDK signs a USDC EIP-3009 authorization
   locally and the request is retried with a `PAYMENT-SIGNATURE` header.
4. HTTP 200 with the data, plus a `PAYMENT-RESPONSE` header carrying the
   transaction hash. A 404 or an error is never charged. Settlement is
   gasless for the payer.

## Examples

- `examples/market_brief.py` — the $0.01 proof call.
- `examples/event_risk.py` — the $0.05 proof call.

Run with `AGENT_PRIVATE_KEY` set:

```bash
AGENT_PRIVATE_KEY=0x... python examples/market_brief.py
```

## Tests

```bash
python -m pytest tests/ -v
```

`tests/test_unpaid.py` hits the live API without a key and verifies the 402
flow (price returned, no payment attempted). `tests/test_signing.py` proves
the EIP-3009 signature round-trips offline with a throwaway key — no network,
no funds.

## License

MIT. Market data returned by the API is not investment advice.
