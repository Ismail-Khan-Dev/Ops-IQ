import pytest

from ecommerce_ops.tools.registry import Tool, ToolRegistry


class DummyTool(Tool):
    def __init__(self):
        self.name = "dummy"
        self.description = "A test tool"

    async def run(self, **kwargs) -> dict:
        return {"result": f"ran with {kwargs}"}


def clear_registry():
    ToolRegistry._tools = {}


@pytest.mark.asyncio
async def test_register_and_run_tool():
    clear_registry()
    ToolRegistry.register(DummyTool())
    result = await ToolRegistry.run_tool("dummy", key="val")
    assert result["result"] == "ran with {'key': 'val'}"


@pytest.mark.asyncio
async def test_run_unknown_tool():
    clear_registry()
    with pytest.raises(ValueError):
        await ToolRegistry.run_tool("nonexistent")


def test_get_tool():
    clear_registry()
    ToolRegistry.register(DummyTool())
    tool = ToolRegistry.get("dummy")
    assert tool is not None
    assert tool.name == "dummy"


def test_list_tools():
    clear_registry()
    ToolRegistry.register(DummyTool())
    tools = ToolRegistry.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "dummy"


@pytest.mark.asyncio
async def test_multiple_tools():
    clear_registry()

    class ToolA(Tool):
        name = "a"
        description = "tool a"
        async def run(self, **kw): return {"from": "a"}

    class ToolB(Tool):
        name = "b"
        description = "tool b"
        async def run(self, **kw): return {"from": "b"}

    ToolRegistry.register(ToolA())
    ToolRegistry.register(ToolB())

    r1 = await ToolRegistry.run_tool("a")
    r2 = await ToolRegistry.run_tool("b")
    assert r1["from"] == "a"
    assert r2["from"] == "b"
    assert len(ToolRegistry.list_tools()) == 2
