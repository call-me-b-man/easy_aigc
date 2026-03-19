"""
Provider 抽象基类 — 所有图片 API 提供商的统一接口
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.schemas import ModelInfo


@dataclass
class ProviderResult:
    """统一的图片生成结果"""
    image_url: str | None = None
    image_base64: str | None = None
    seed: int | None = None
    model_used: str = ""
    provider_name: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


class ImageProvider(ABC):
    """
    图片 API 提供商的抽象基类

    所有 Provider 实现需继承此类并实现以下方法:
    - generate_image()  : 核心图片生成能力
    - list_models()     : 列出支持的模型
    - health_check()    : 健康检查
    """

    name: str = ""  # 提供商标识, 如 "siliconflow", "evolink"

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        reference_image: str | None = None,
        model: str | None = None,
        image_size: str = "1024x1024",
        num_inference_steps: int = 50,
        cfg: float = 4.0,
        seed: int | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        """
        生成图片

        Args:
            prompt: 文本提示词
            reference_image: 参考图片 (base64 或 URL)
            model: 模型标识
            image_size: 输出尺寸 "widthxheight"
            num_inference_steps: 推理步数
            cfg: CFG 引导强度
            seed: 随机种子
            **kwargs: Provider 特有参数

        Returns:
            ProviderResult 统一结果
        """

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """返回该提供商支持的模型列表"""

    @abstractmethod
    async def health_check(self) -> bool:
        """检查提供商 API 是否可用"""
