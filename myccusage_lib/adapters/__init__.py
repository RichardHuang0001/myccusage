"""
myccusage_lib.adapters:
Agent 原生适配器统一导出注册表:
包含 8 大 Agent 的高性能适配器实现
该模块用于集中管理所有 Agent 的数据源适配器，提供统一的注册和获取机制。
"""

from __future__ import annotations

from .base import BaseAgentAdapter
from .workbuddy import WorkBuddyAdapter
from .claude import ClaudeAdapter
from .hermes import HermesAdapter
from .opencode import OpenCodeAdapter
from .codex import CodexAdapter
from .pi import PiAdapter
from .grok import GrokAdapter
from .agy import AntigravityAdapter

# 适配器注册表字典，键为 Agent 类型标识，值为具体的适配器实例
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
    """
    获取指定 Agent 适配器实例
    
    参数:
        agent_type (str): Agent 类型的短标识，例如 'claude', 'codex'
        
    返回:
        BaseAgentAdapter: 对应的适配器实例
        
    异常:
        ValueError: 当请求了不支持的 Agent 类型时抛出
    """
    # 检查请求的类型是否在注册表中注册
    if agent_type not in ADAPTERS:
        raise ValueError(f"未知 Agent 类型: {agent_type}，支持列表: {list(ADAPTERS.keys())}")
    # 返回注册的适配器实例
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
