"""
主体提取服务 — 从输入图片中提取主体
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models.schemas import ExtractSubjectResponse, TaskStatus
from app.providers.base import ProviderResult
from app.providers.registry import ProviderRegistry
from app.services.prompt_engine import PromptEngine
from app.utils.image_utils import image_to_base64
from app.utils.storage import StorageManager

logger = logging.getLogger(__name__)


class SubjectExtractor:
    """
    主体提取服务

    从输入图片中提取主体，去除背景，
    通过 PromptEngine 支持 Prompt 动态注入。
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        storage: StorageManager,
        prompt_engine: PromptEngine,
    ) -> None:
        self._registry = registry
        self._storage = storage
        self._prompt_engine = prompt_engine

    async def extract(
        self,
        image_content: bytes,
        image_filename: str = "original.png",
        provider_name: str | None = None,
        model: str | None = None,
        custom_prompt: str | None = None,
        prompt_variables: dict[str, str] | None = None,
        image_size: str | None = None,
    ) -> ExtractSubjectResponse:
        """
        执行主体提取

        Args:
            image_content: 上传的图片字节数据
            image_filename: 原始文件名
            provider_name: 指定 Provider (为空用默认)
            model: 指定模型 (为空用配置默认)
            custom_prompt: 完全自定义 Prompt (最高优先级)
            prompt_variables: 模板变量注入
            image_size: 输出图片尺寸

        Returns:
            ExtractSubjectResponse
        """
        settings = get_settings()
        task_id = uuid.uuid4().hex[:12]

        # 1. 创建任务目录并保存原始图片
        task_dir = self._storage.get_task_dir(task_id)
        ext = Path(image_filename).suffix or ".png"
        await self._storage.save_uploaded_image(
            image_content, task_dir, "original", ext
        )

        # 2. 渲染 Prompt
        prompt = self._prompt_engine.render_extraction_prompt(
            custom_prompt=custom_prompt,
            **(prompt_variables or {}),
        )

        # 3. 获取 Provider
        provider = self._registry.get(
            provider_name or settings.default_provider
        )
        actual_model = model or settings.subject_extraction_model

        # 4. 将图片转为 base64
        original_path = task_dir / f"original{ext}"
        image_b64 = image_to_base64(original_path)

        # 5. 调用 Provider
        logger.info(
            "开始主体提取: task=%s, provider=%s, model=%s",
            task_id,
            provider.name,
            actual_model,
        )
        try:
            result = await provider.generate_image(
                prompt=prompt,
                reference_image=image_b64,
                model=actual_model,
                image_size=image_size or "1024x1024",
                num_inference_steps=settings.num_inference_steps,
                cfg=settings.cfg_scale,
            )

            # 6. 保存结果图片
            saved_path = await self._storage.save_from_result(
                result, task_dir, "subject"
            )

            # 7. 保存元数据
            metadata: dict[str, Any] = {
                "task_id": task_id,
                "type": "subject_extraction",
                "provider": provider.name,
                "model": actual_model,
                "prompt_used": prompt,
                "seed": result.seed,
                "subject_image": str(saved_path) if saved_path else None,
            }
            self._storage.save_metadata(task_dir, metadata)

            return ExtractSubjectResponse(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                subject_image_path=str(saved_path) if saved_path else None,
                prompt_used=prompt,
                provider_used=provider.name,
                model_used=actual_model,
            )

        except Exception as e:
            logger.error("主体提取失败: %s", str(e), exc_info=True)
            # 保存错误信息
            self._storage.save_metadata(task_dir, {
                "task_id": task_id,
                "type": "subject_extraction",
                "status": "failed",
                "error": str(e),
            })
            return ExtractSubjectResponse(
                task_id=task_id,
                status=TaskStatus.FAILED,
                prompt_used=prompt,
                provider_used=provider.name,
                model_used=actual_model,
                error=str(e),
            )
