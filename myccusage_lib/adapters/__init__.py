"""
myccusage_lib.adapters:
Agent 原生适配器统一导出注册表:
包含 8 大 Agent 的高性能适配器实现
"""

from .base import BaseAgentAdapter
from .workbuddy import WorkBuddyAdapter
from .claude import ClaudeAdapter
from .hermes import HermesAdapter
from .opencode import OpenCodeAdapter
from .codex import CodexAdapter
from .pi import PiAdapter
from .grok import GrokAdapter
from .agy import AntigravityAdapter

ADAPTERS = {
    "workbuddy": WorkBuddyAdapter(),
    "claude": ClaudeAdapter(),
    "hermes": HermesAdapter(),
    "opencode": OpenCodeAdapter(),
    "codex": CodexAdapter(),
    "pi": PiAdapter(),
    "grok": GrokAdapter(),
    "agy": AntigravityAdapter(),
}

def get_adapter(agent_type: str) -> BaseAgentAdapter:
    """获取指定 Agent 适配器实例"""
    if agent_type not in ADAPTERS:
        raise ValueError(f"未知 Agent 类型: {agent_type}，支持列表: {list(ADAPTERS.keys())}")
    return ADAPTERS[agent_type]

__all__ = [
    "BaseAgentAdapter",
    "ADAPTERS",
    "get_adapter",
    "WorkBuddyAdapter",
    "ClaudeAdapter",
    "HermesAdapter",
    "OpenCodeAdapter",
    "CodexAdapter",
    "PiAdapter",
    "GrokAdapter",
    "AntigravityAdapter",
]
