"""配置化 Agent middleware 扩展口。

这个模块只描述“怎么从 config.yaml 声明外部 middleware”，不承载任何
业务规则。NL2SQL Evidence Gate 等企业能力通过 ``use`` 动态加载，从而
避免 DeerFlow 核心直接依赖项目自有代码。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentMiddlewareEntry(BaseModel):
    """单个 middleware 配置项。

    ``use`` 使用 ``module:ClassName`` 格式，加载器会实例化这个类，并把
    ``config`` 原样传入。这样 DeerFlow 只负责装配，具体策略由外部实现。
    """

    name: str = Field(description="Middleware instance name used for logs and diagnostics")
    enabled: bool = Field(default=True, description="Whether this middleware entry is enabled")
    use: str = Field(description="Python class path in module:ClassName format")
    config: dict[str, Any] = Field(default_factory=dict, description="Middleware-specific configuration")


class AgentMiddlewaresConfig(BaseModel):
    """按 agent_name 注册的 middleware 配置。

    ``enabled`` 是全局开关；``agents`` 的 key 必须匹配运行时 agent_name。
    未匹配到 agent 时返回空列表，保证默认 agent 和其他自定义 agent 行为不变。
    """

    enabled: bool = Field(default=False, description="Enable config-driven agent middleware loading")
    agents: dict[str, list[AgentMiddlewareEntry]] = Field(
        default_factory=dict,
        description="Mapping from agent_name to configured middleware entries",
    )
