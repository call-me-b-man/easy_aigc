"""
Provider 注册中心 — 统一管理所有提供商实例
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.providers.base import ImageProvider

logger = logging.getLogger(__name__)


class ProviderNotFoundError(Exception):
    """Provider 未找到"""


class ProviderRegistry:
    """
    Provider 注册中心

    Usage:
        registry = ProviderRegistry()
        registry.register(SiliconFlowProvider(...))
        registry.register(EvolinkProvider(...))

        provider = registry.get("siliconflow")
        # 或使用默认
        provider = registry.get_default()
    """

    def __init__(self) -> None:
        self._providers: dict[str, ImageProvider] = {}

    def register(self, provider: ImageProvider) -> None:
        """注册一个 Provider 实例"""
        self._providers[provider.name] = provider
        logger.info("Provider 已注册: %s", provider.name)

    def unregister(self, name: str) -> None:
        """注销一个 Provider"""
        if name in self._providers:
            del self._providers[name]
            logger.info("Provider 已注销: %s", name)

    def get(self, name: str) -> ImageProvider:
        """
        按名称获取 Provider

        Raises:
            ProviderNotFoundError: 名称不存在
        """
        provider = self._providers.get(name)
        if provider is None:
            available = list(self._providers.keys())
            raise ProviderNotFoundError(
                f"Provider '{name}' 未找到。可用: {available}"
            )
        return provider

    def get_default(self) -> ImageProvider:
        """获取配置中指定的默认 Provider"""
        settings = get_settings()
        return self.get(settings.default_provider)

    def list_all(self) -> dict[str, ImageProvider]:
        """返回所有已注册的 Provider"""
        return dict(self._providers)

    def list_names(self) -> list[str]:
        """返回所有已注册的 Provider 名称"""
        return list(self._providers.keys())
