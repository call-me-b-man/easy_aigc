"""
SiliconFlow Provider — 硅基流动图片生成 API 实现

API 端点: POST https://api.siliconflow.cn/v1/images/generations
特点: 同步返回图片 URL（有效期 1 小时，需立即下载）
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import ProviderConfig, get_settings
from app.models.schemas import ModelInfo
from app.providers.base import ImageProvider, ProviderResult

logger = logging.getLogger(__name__)

# 重试配置
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # 指数退避基数(秒)
REQUEST_TIMEOUT = 120.0  # 请求超时(秒)


class SiliconFlowProvider(ImageProvider):
    """SiliconFlow (硅基流动) 图片生成 Provider"""

    name = "siliconflow"

    # 该 Provider 支持的模型列表
    SUPPORTED_MODELS = [
        ModelInfo(
            id="Qwen/Qwen-Image-Edit-2509",
            name="Qwen Image Edit",
            capabilities=["img2img", "edit", "text_render"],
            provider="siliconflow",
        ),
        ModelInfo(
            id="black-forest-labs/FLUX.1-Kontext-dev",
            name="FLUX.1 Kontext Dev",
            capabilities=["img2img", "edit", "style_transfer"],
            provider="siliconflow",
        ),
        ModelInfo(
            id="Kwai-Kolors/Kolors",
            name="Kolors",
            capabilities=["text2img"],
            provider="siliconflow",
        ),
    ]

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")

    def _get_api_key(self) -> str:
        """动态获取最新 API Key（支持运行时通过 API 更新）"""
        settings = get_settings()
        cfg = settings.providers.get(self.name)
        return (cfg.api_key if cfg else None) or self._config.api_key

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_api_key()}",
            "Content-Type": "application/json",
        }

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
        调用 SiliconFlow 图片生成 API

        SiliconFlow 同步返回图片 URL, URL 有效期仅 1 小时
        """
        actual_model = model or "Qwen/Qwen-Image-Edit-2509"

        payload: dict[str, Any] = {
            "model": actual_model,
            "prompt": prompt,
            "num_inference_steps": num_inference_steps,
        }

        # Qwen 模型使用 cfg 字段; Kolors 使用 guidance_scale
        if "Qwen" in actual_model:
            payload["cfg"] = cfg
        else:
            payload["guidance_scale"] = cfg

        # 图生图: 传入参考图
        if reference_image:
            payload["image"] = reference_image

        # 图片尺寸 (Qwen-Image-Edit 不支持 image_size)
        if "Qwen-Image-Edit" not in actual_model:
            payload["image_size"] = image_size

        if seed is not None:
            payload["seed"] = seed

        # 额外参数 (如 image2, image3 for Qwen-Image-Edit-2509)
        for key in ("image2", "image3", "negative_prompt", "batch_size"):
            if key in kwargs:
                payload[key] = kwargs[key]

        # 带重试的请求
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/images/generations",
                        headers=self._headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()

                    # 解析响应
                    images = data.get("images", [])
                    image_url = images[0]["url"] if images else None

                    result = ProviderResult(
                        image_url=image_url,
                        seed=data.get("seed"),
                        model_used=actual_model,
                        provider_name=self.name,
                        raw_response=data,
                    )
                    logger.info(
                        "SiliconFlow 生成成功: model=%s, seed=%s",
                        actual_model,
                        result.seed,
                    )
                    return result

            except httpx.HTTPStatusError as e:
                last_error = e
                error_body = e.response.text[:500]
                logger.warning(
                    "SiliconFlow API 错误 (尝试 %d/%d): HTTP %s\n%s",
                    attempt + 1,
                    MAX_RETRIES,
                    e.response.status_code,
                    error_body,
                )
            except httpx.RequestError as e:
                last_error = e
                logger.warning(
                    "SiliconFlow 请求错误 (尝试 %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    str(e),
                )

            # 指数退避
            if attempt < MAX_RETRIES - 1:
                import asyncio
                wait = RETRY_BACKOFF ** (attempt + 1)
                logger.info("等待 %.1f 秒后重试...", wait)
                await asyncio.sleep(wait)

        # 构建友好的错误消息
        if isinstance(last_error, httpx.HTTPStatusError):
            detail = last_error.response.text[:300]
            raise RuntimeError(
                f"SiliconFlow API 返回 HTTP {last_error.response.status_code}: {detail}"
            )
        raise RuntimeError(
            f"SiliconFlow API 调用失败 (已重试 {MAX_RETRIES} 次): {last_error}"
        )

    def list_models(self) -> list[ModelInfo]:
        return list(self.SUPPORTED_MODELS)

    async def health_check(self) -> bool:
        """简单检查 API 连通性"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers=self._headers,
                )
                return response.status_code == 200
        except Exception:
            return False
