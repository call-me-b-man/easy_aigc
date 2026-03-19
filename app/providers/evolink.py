"""
Evolink Provider — Evolink 图片生成 API 实现

API 端点: POST https://api.evolink.ai/v1/images/generations
特点: 异步模式，返回 task_id 需轮询获取结果，URL 有效期 24 小时
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import ProviderConfig, get_settings
from app.models.schemas import ModelInfo
from app.providers.base import ImageProvider, ProviderResult

logger = logging.getLogger(__name__)

# 配置
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
REQUEST_TIMEOUT = 120.0
POLL_INTERVAL = 3.0  # 轮询间隔(秒)
POLL_MAX_WAIT = 300.0  # 最大等待时间(秒)


class EvolinkProvider(ImageProvider):
    """Evolink 图片生成 Provider"""

    name = "evolink"

    SUPPORTED_MODELS = [
        ModelInfo(
            id="gpt-4o-image",
            name="GPT-4o Image",
            capabilities=["text2img", "img2img", "edit"],
            provider="evolink",
        ),
        ModelInfo(
            id="seedream-4.5",
            name="Seedream 4.5",
            capabilities=["text2img", "img2img"],
            provider="evolink",
        ),
        ModelInfo(
            id="wan2.5-i2i",
            name="Wan2.5 Image to Image",
            capabilities=["img2img"],
            provider="evolink",
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
        调用 Evolink 图片生成 API

        Evolink 使用异步模式:
        1. 提交任务 → 获得 task_id
        2. 轮询 task 状态 → 获取结果 URL
        """
        actual_model = model or "gpt-4o-image"

        payload: dict[str, Any] = {
            "model": actual_model,
            "prompt": prompt,
            "image_size": image_size,
        }

        if reference_image:
            payload["image"] = reference_image

        if seed is not None:
            payload["seed"] = seed

        if num_inference_steps:
            payload["num_inference_steps"] = num_inference_steps

        # 额外参数
        for key in ("negative_prompt", "batch_size", "mask"):
            if key in kwargs:
                payload[key] = kwargs[key]

        # 步骤 1: 提交任务
        submit_data = await self._submit_task(payload)
        task_id = self._extract_task_id(submit_data)

        if task_id:
            # 步骤 2: 轮询任务结果
            result_data = await self._poll_task(task_id)
        else:
            # 某些模型可能同步返回
            result_data = submit_data

        # 解析结果
        images = result_data.get("images", [])
        if not images:
            # 尝试从 data.output 解析
            output = result_data.get("output", result_data.get("data", {}))
            if isinstance(output, dict):
                images = output.get("images", [])

        image_url = None
        if images:
            first = images[0]
            image_url = first if isinstance(first, str) else first.get("url")

        result = ProviderResult(
            image_url=image_url,
            seed=result_data.get("seed"),
            model_used=actual_model,
            provider_name=self.name,
            raw_response=result_data,
        )
        logger.info(
            "Evolink 生成成功: model=%s, has_url=%s",
            actual_model,
            image_url is not None,
        )
        return result

    async def _submit_task(self, payload: dict) -> dict:
        """提交生成任务（带重试）"""
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
                    return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    "Evolink 提交错误 (尝试 %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    e.response.status_code,
                )
            except httpx.RequestError as e:
                last_error = e
                logger.warning(
                    "Evolink 请求错误 (尝试 %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    str(e),
                )

            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"Evolink 任务提交失败 (已重试 {MAX_RETRIES} 次): {last_error}"
        )

    @staticmethod
    def _extract_task_id(data: dict) -> str | None:
        """从提交响应中提取 task_id"""
        # 尝试多种可能的字段名
        for key in ("task_id", "taskId", "id", "request_id"):
            if key in data:
                return data[key]
        # 如果已经有 images 字段，说明是同步返回
        if data.get("images"):
            return None
        return None

    async def _poll_task(self, task_id: str) -> dict:
        """轮询任务状态直到完成"""
        elapsed = 0.0
        while elapsed < POLL_MAX_WAIT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self._base_url}/images/generations/{task_id}",
                        headers=self._headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                    status = data.get("status", "").lower()
                    if status in ("completed", "success", "succeeded"):
                        logger.info("Evolink 任务完成: %s", task_id)
                        return data
                    elif status in ("failed", "error"):
                        error_msg = data.get("error", "未知错误")
                        raise RuntimeError(
                            f"Evolink 任务失败: {error_msg}"
                        )

                    logger.debug(
                        "Evolink 任务进行中: %s, 状态: %s, 已等 %.0fs",
                        task_id,
                        status,
                        elapsed,
                    )

            except httpx.RequestError as e:
                logger.warning("轮询请求错误: %s", str(e))

        raise TimeoutError(
            f"Evolink 任务超时 ({POLL_MAX_WAIT}s): {task_id}"
        )

    def list_models(self) -> list[ModelInfo]:
        return list(self.SUPPORTED_MODELS)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers=self._headers,
                )
                return response.status_code == 200
        except Exception:
            return False
