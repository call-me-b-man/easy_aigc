"""
多视角生成服务 — 基于主体图片生成多个视角的一致性图片
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models.schemas import MultiViewResponse, TaskStatus, ViewResult
from app.providers.registry import ProviderRegistry
from app.services.prompt_engine import PromptEngine
from app.utils.image_utils import image_to_base64
from app.utils.storage import StorageManager

logger = logging.getLogger(__name__)


class MultiViewGenerator:
    """
    多视角生成服务

    基于提取的主体图片，并发生成多个视角的一致性图片。
    通过 PromptEngine 支持按视角自定义 Prompt。
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

    async def generate(
        self,
        subject_image_path: str,
        views: list[str] | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        custom_prompts: dict[str, str] | None = None,
        prompt_variables: dict[str, str] | None = None,
        image_size: str | None = None,
        task_id: str | None = None,
        task_dir: Path | None = None,
    ) -> MultiViewResponse:
        """
        并发生成多个视角的图片

        Args:
            subject_image_path: 主体图片路径
            views: 视角列表 (为空用默认配置)
            provider_name: 指定 Provider
            model: 指定模型
            custom_prompts: 按视角自定义 Prompt {视角名: prompt}
            prompt_variables: 全局模板变量注入
            image_size: 输出尺寸
            task_id: 任务ID (已有则复用)
            task_dir: 任务目录 (已有则复用)

        Returns:
            MultiViewResponse
        """
        settings = get_settings()
        task_id = task_id or uuid.uuid4().hex[:12]

        # 1. 准备
        if task_dir is None:
            task_dir = self._storage.get_task_dir(task_id)

        actual_views = views or settings.default_views
        provider = self._registry.get(
            provider_name or settings.default_provider
        )
        actual_model = model or settings.multiview_generation_model

        # 2. 读取主体图片为 base64
        subject_b64 = image_to_base64(subject_image_path)

        # 3. 并发生成各视角
        logger.info(
            "开始多视角生成: task=%s, views=%s, provider=%s",
            task_id,
            actual_views,
            provider.name,
        )

        tasks = []
        for view_name in actual_views:
            # 渲染该视角的 Prompt
            prompt = self._prompt_engine.render_multiview_prompt(
                view_name=view_name,
                custom_prompt=(custom_prompts or {}).get(view_name),
                **(prompt_variables or {}),
            )
            tasks.append(
                self._generate_single_view(
                    view_name=view_name,
                    prompt=prompt,
                    subject_b64=subject_b64,
                    provider=provider,
                    model=actual_model,
                    image_size=image_size or "1024x1024",
                    task_dir=task_dir,
                    settings=settings,
                )
            )

        view_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. 整理结果
        final_views: list[ViewResult] = []
        all_success = True
        for view_name, result in zip(actual_views, view_results):
            if isinstance(result, Exception):
                logger.error("视角 %s 生成失败: %s", view_name, str(result))
                final_views.append(ViewResult(
                    view_name=view_name,
                    status=TaskStatus.FAILED,
                    prompt_used=str(result),
                ))
                all_success = False
            else:
                final_views.append(result)

        # 5. 保存元数据
        metadata: dict[str, Any] = {
            "task_id": task_id,
            "type": "multiview_generation",
            "provider": provider.name,
            "model": actual_model,
            "views": [v.model_dump() for v in final_views],
        }
        self._storage.save_metadata(task_dir, metadata)

        overall_status = TaskStatus.COMPLETED if all_success else TaskStatus.FAILED

        return MultiViewResponse(
            task_id=task_id,
            status=overall_status,
            views=final_views,
            provider_used=provider.name,
            model_used=actual_model,
        )

    async def _generate_single_view(
        self,
        view_name: str,
        prompt: str,
        subject_b64: str,
        provider: Any,
        model: str,
        image_size: str,
        task_dir: Path,
        settings: Any,
    ) -> ViewResult:
        """生成单个视角的图片"""
        try:
            result = await provider.generate_image(
                prompt=prompt,
                reference_image=subject_b64,
                model=model,
                image_size=image_size,
                num_inference_steps=settings.num_inference_steps,
                cfg=settings.cfg_scale,
            )

            # 保存图片
            filename = f"view_{view_name}"
            saved_path = await self._storage.save_from_result(
                result, task_dir, filename
            )

            return ViewResult(
                view_name=view_name,
                image_path=str(saved_path) if saved_path else None,
                prompt_used=prompt,
                status=TaskStatus.COMPLETED,
            )

        except Exception as e:
            logger.error("视角 %s 生成异常: %s", view_name, str(e))
            raise
