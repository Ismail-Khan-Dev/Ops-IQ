import abc
import logging
from typing import Any, ClassVar, Dict, List, Optional

logger = logging.getLogger("ecommerce_ops.tools.registry")


class Tool(abc.ABC):
    name: str
    description: str

    @abc.abstractmethod
    async def run(self, **kwargs) -> Any: ...


class ToolRegistry:
    _tools: ClassVar[Dict[str, Tool]] = {}

    @classmethod
    def register(cls, tool: Tool) -> None:
        cls._tools[tool.name] = tool
        logger.info("Tool registered: %s — %s", tool.name, tool.description)

    @classmethod
    def get(cls, name: str) -> Optional[Tool]:
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> List[Dict[str, str]]:
        return [{"name": t.name, "description": t.description} for t in cls._tools.values()]

    @classmethod
    async def run_tool(cls, name: str, **kwargs) -> Any:
        tool = cls.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        logger.info("Running tool %s with args: %s", name, kwargs)
        return await tool.run(**kwargs)
