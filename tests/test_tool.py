"""Tool factory tests: schemas, names, and the no-key paid-call behaviour."""

import json

from blockchain_iq_langchain import make_tool, make_tools
from blockchain_iq_langchain.resources import RESOURCES


def test_factory_builds_one_tool_per_resource():
    tools = make_tools()
    assert len(tools) == len(RESOURCES)
    names = {t.name for t in tools}
    assert "blockchain_iq_brief" in names
    assert "blockchain_iq_event_risk" in names
    assert "blockchain_iq_catalog" in names
    assert all(n.startswith("blockchain_iq_") for n in names)


def test_brief_tool_has_no_required_args():
    tool = make_tool("brief")
    assert tool.name == "blockchain_iq_brief"
    assert "$0.01" in tool.description
    assert tool.args == {}


def test_path_params_are_required():
    tool = make_tool("dashboard")
    assert "slug" in tool.args
    tool = make_tool("research")
    assert "coin" in tool.args


def test_brief_tool_without_key_returns_payment_required_json():
    tool = make_tool("brief")
    result = json.loads(tool.invoke({}))
    assert result["error"] == "payment_required"
    assert result["price_usd"] == 0.01
    assert result["resource"] == "brief"


def test_catalog_tool_is_free_and_works_live():
    tool = make_tool("catalog")
    result = json.loads(tool.invoke({}))
    assert result["x402Version"] == 2
    assert result["_payment"] is None
