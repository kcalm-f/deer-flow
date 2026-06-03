"""从配置动态加载 agent 级 middleware。

这是 DeerFlow 的通用扩展口：它只关心 agent_name、动态 import 和实例化，
不认识 NL2SQL、证据链或任何企业业务规则。加载失败时采用 fail-safe：
记录错误并跳过该 middleware，避免一个外部扩展影响默认 agent 启动。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from deerflow.config.agent_middlewares_config import AgentMiddlewareEntry, AgentMiddlewaresConfig
from deerflow.reflection import resolve_variable

logger = logging.getLogger(__name__)


def _get_agent_middlewares_config(app_config: Any) -> AgentMiddlewaresConfig:
    """从 AppConfig 或测试替身中读取配置。

    测试里会传 ``SimpleNamespace``，生产里是 ``AppConfig``。这里保持宽松，
    是为了让 loader 本身小而稳定，不把 AppConfig 变成硬依赖。
    """

    raw_config = getattr(app_config, "agent_middlewares", None)
    if raw_config is None:
        return AgentMiddlewaresConfig()
    if isinstance(raw_config, AgentMiddlewaresConfig):
        return raw_config
    return AgentMiddlewaresConfig.model_validate(raw_config)


def _instantiate_middleware(
    entry: AgentMiddlewareEntry,
    *,
    agent_name: str,
    app_config: Any,
) -> AgentMiddleware | None:
    """加载并实例化单个 middleware。

    外部类统一接收 ``config``、``agent_name``、``middleware_name`` 和
    ``app_config``。如果类不是 ``AgentMiddleware`` 子类，或实例化失败，
    这里都记录错误后返回 None。
    """

    middleware_cls = resolve_variable(entry.use, expected_type=type)
    if not issubclass(middleware_cls, AgentMiddleware):
        logger.error(
            "Failed to load agent middleware %s for agent %s: %s is not an AgentMiddleware subclass",
            entry.name,
            agent_name,
            entry.use,
        )
        return None

    instance = middleware_cls(
        config=entry.config,
        agent_name=agent_name,
        middleware_name=entry.name,
        app_config=app_config,
    )
    if not isinstance(instance, AgentMiddleware):
        logger.error(
            "Failed to load agent middleware %s for agent %s: %s did not create an AgentMiddleware instance",
            entry.name,
            agent_name,
            entry.use,
        )
        return None
    return instance


def load_agent_middlewares(
    agent_name: str | None,
    *,
    app_config: Any,
) -> list[AgentMiddleware]:
    """加载当前 agent_name 对应的配置化 middleware。

    未配置、全局关闭、agent_name 为空、agent 不匹配时都返回空列表。这保证
    新扩展口对默认 DeerFlow 行为是透明的。
    """

    if not agent_name:
        return []

    config = _get_agent_middlewares_config(app_config)
    if not config.enabled:
        return []

    entries = config.agents.get(agent_name, [])
    middlewares: list[AgentMiddleware] = []
    for entry in entries:
        if not entry.enabled:
            continue
        try:
            middleware = _instantiate_middleware(entry, agent_name=agent_name, app_config=app_config)
        except Exception:
            logger.exception(
                "Failed to load agent middleware %s for agent %s from %s",
                entry.name,
                agent_name,
                entry.use,
            )
            continue
        if middleware is not None:
            middlewares.append(middleware)
    return middlewares
