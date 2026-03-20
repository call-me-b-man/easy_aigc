"""
模特生成服务 — 文生图创建模特 + 图生图迭代完善（追加视角/姿势参考图）
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models.schemas import (
    EnrichModelRequest,
    ModelCardResponse,
    ModelListItem,
    ModelReference,
    ReferenceType,
    TaskStatus,
)
from app.providers.registry import ProviderRegistry
from app.services.multiview_generator import MultiViewGenerator
from app.services.prompt_engine import PromptEngine
from app.utils.image_utils import image_to_base64
from app.utils.storage import StorageManager

logger = logging.getLogger(__name__)


class ModelGenerator:
    """
    模特生成服务

    - create()          : 文生图创建模特 + 自动生成默认视角参考图
    - create_from_image(): 从上传图片创建模特
    - enrich()          : 图生图追加参考图（新角度/姿势），保持主体一致性
    - list_models()     : 列出已保存模特
    - get_model()       : 获取模特卡详情
    - delete_model()    : 删除模特
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        storage: StorageManager,
        prompt_engine: PromptEngine,
        multiview: MultiViewGenerator,
        models_base_path: str | Path = "./output/models",
    ) -> None:
        self._registry = registry
        self._storage = storage
        self._prompt_engine = prompt_engine
        self._multiview = multiview
        self._models_path = Path(models_base_path)
        self._models_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 文生图创建模特
    # ------------------------------------------------------------------

    async def create(
        self,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
        gender: str = "female",
        style: str = "时尚写真",
        custom_prompt: str | None = None,
        prompt_variables: dict[str, str] | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        image_size: str | None = None,
        views: list[str] | None = None,
        multiview_provider: str | None = None,
        multiview_model: str | None = None,
    ) -> ModelCardResponse:
        """文生图创建模特 → 自动生成默认视角参考图"""
        settings = get_settings()
        model_id = uuid.uuid4().hex[:12]
        model_dir = self._models_path / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()

        # 1. 渲染文生图 Prompt
        variables = dict(prompt_variables or {})
        variables.setdefault("gender", gender)
        variables.setdefault("model_description", description or "young professional model")

        prompt = self._prompt_engine.render_model_generation_prompt(
            custom_prompt=custom_prompt, **variables
        )

        # 2. 文生图生成原始正面照
        provider = self._registry.get(
            provider_name or settings.default_provider
        )
        actual_model = model or settings.model_generation_model

        logger.info(
            "文生图创建模特: id=%s, provider=%s, model=%s",
            model_id, provider.name, actual_model,
        )

        try:
            result = await provider.generate_image(
                prompt=prompt,
                model=actual_model,
                image_size=image_size or "1024x1024",
                num_inference_steps=settings.num_inference_steps,
                cfg=settings.cfg_scale,
            )

            # 保存原始图片
            saved_path = await self._storage.save_from_result(
                result, model_dir, "original"
            )

        except Exception as e:
            logger.error("文生图创建模特失败: %s", str(e), exc_info=True)
            # 保存失败状态
            metadata = self._build_metadata(
                model_id=model_id, name=name, description=description,
                tags=tags, gender=gender, style=style,
                original_prompt=prompt, now=now, status="failed",
                error=str(e),
            )
            self._save_model_metadata(model_dir, metadata)
            return ModelCardResponse(
                model_id=model_id, name=name, status=TaskStatus.FAILED,
                error=str(e), original_prompt=prompt,
            )

        # 3. 自动生成多视角参考图
        actual_views = views or settings.default_views
        references: list[ModelReference] = []

        try:
            mv_result = await self._multiview.generate(
                subject_image_path=str(saved_path),
                views=actual_views,
                provider_name=multiview_provider or provider_name,
                model=multiview_model,
                prompt_variables={"subject_description": description or "the model"},
                task_id=model_id,
                task_dir=model_dir,
            )

            for vr in mv_result.views:
                if vr.status == TaskStatus.COMPLETED and vr.image_path:
                    references.append(ModelReference(
                        name=vr.view_name,
                        type=ReferenceType.VIEW,
                        image_path=vr.image_path,
                        prompt_used=vr.prompt_used,
                        created_at=now,
                    ))
        except Exception as e:
            logger.warning("多视角生成部分失败: %s", str(e))

        # 4. 保存模特卡元数据
        metadata = self._build_metadata(
            model_id=model_id, name=name, description=description,
            tags=tags, gender=gender, style=style,
            original_prompt=prompt, now=now,
            original_image=str(saved_path) if saved_path else None,
            references=references,
        )
        self._save_model_metadata(model_dir, metadata)

        # 5. 复制原始图作为缩略图
        if saved_path and saved_path.exists():
            thumbnail_path = model_dir / f"thumbnail{saved_path.suffix}"
            shutil.copy2(saved_path, thumbnail_path)

        return self._metadata_to_response(metadata)

    # ------------------------------------------------------------------
    # 从图片创建模特
    # ------------------------------------------------------------------

    async def create_from_image(
        self,
        image_content: bytes,
        image_filename: str = "original.png",
        name: str = "",
        description: str = "",
        tags: list[str] | None = None,
        gender: str = "female",
        style: str = "时尚写真",
        views: list[str] | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        image_size: str | None = None,
    ) -> ModelCardResponse:
        """从上传图片创建模特 → 自动生成多视角参考图"""
        settings = get_settings()
        model_id = uuid.uuid4().hex[:12]
        model_dir = self._models_path / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()

        # 1. 保存原始图片
        ext = Path(image_filename).suffix or ".png"
        original_path = model_dir / f"original{ext}"
        original_path.write_bytes(image_content)

        # 2. 生成多视角参考图
        actual_views = views or settings.default_views
        references: list[ModelReference] = []

        try:
            mv_result = await self._multiview.generate(
                subject_image_path=str(original_path),
                views=actual_views,
                provider_name=provider_name,
                model=model,
                prompt_variables={"subject_description": description or "the model"},
                image_size=image_size,
                task_id=model_id,
                task_dir=model_dir,
            )

            for vr in mv_result.views:
                if vr.status == TaskStatus.COMPLETED and vr.image_path:
                    references.append(ModelReference(
                        name=vr.view_name,
                        type=ReferenceType.VIEW,
                        image_path=vr.image_path,
                        prompt_used=vr.prompt_used,
                        created_at=now,
                    ))
        except Exception as e:
            logger.warning("多视角生成部分失败: %s", str(e))

        # 3. 保存模特卡
        metadata = self._build_metadata(
            model_id=model_id, name=name, description=description,
            tags=tags, gender=gender, style=style,
            original_prompt=None, now=now,
            original_image=str(original_path),
            references=references,
        )
        self._save_model_metadata(model_dir, metadata)

        # 4. 缩略图
        thumbnail_path = model_dir / f"thumbnail{ext}"
        shutil.copy2(original_path, thumbnail_path)

        return self._metadata_to_response(metadata)

    # ------------------------------------------------------------------
    # 迭代完善模特 (图生图追加参考图)
    # ------------------------------------------------------------------

    async def enrich(
        self,
        model_id: str,
        request: EnrichModelRequest,
    ) -> ModelCardResponse:
        """
        图生图追加参考图 — 保持主体一致性，追加新角度/姿势

        基于模特的原始图片作为参考，生成新的参考图。
        """
        settings = get_settings()
        model_dir = self._models_path / model_id
        metadata = self._load_model_metadata(model_dir)
        if metadata is None:
            return ModelCardResponse(
                model_id=model_id, name="", status=TaskStatus.FAILED,
                error=f"模特 {model_id} 不存在",
            )

        now = datetime.now().isoformat()

        # 找到原始图片作为参考
        original_image = metadata.get("original_image")
        if not original_image or not Path(original_image).exists():
            return ModelCardResponse(
                model_id=model_id, name=metadata.get("name", ""),
                status=TaskStatus.FAILED,
                error="原始图片不存在，无法进行图生图",
            )

        subject_b64 = image_to_base64(original_image)

        # 获取 Provider
        provider = self._registry.get(
            request.provider or settings.default_provider
        )
        actual_model = request.model or settings.multiview_generation_model
        description = metadata.get("description", "the model")

        # 并发生成所有参考图
        async def _gen_single(ref_item):
            # 渲染 Prompt
            variables = dict(request.prompt_variables or {})
            variables.setdefault("model_description", description)
            variables.setdefault("subject_description", description)

            if ref_item.type == ReferenceType.VIEW:
                prompt = self._prompt_engine.render_multiview_prompt(
                    view_name=ref_item.name,
                    custom_prompt=ref_item.custom_prompt,
                    **variables,
                )
            else:
                prompt = self._prompt_engine.render_model_pose_prompt(
                    pose_name=ref_item.name,
                    custom_prompt=ref_item.custom_prompt,
                    **variables,
                )

            result = await provider.generate_image(
                prompt=prompt,
                reference_image=subject_b64,
                model=actual_model,
                image_size=request.image_size or "1024x1024",
                num_inference_steps=settings.num_inference_steps,
                cfg=settings.cfg_scale,
            )

            filename = f"ref_{ref_item.name}"
            saved_path = await self._storage.save_from_result(
                result, model_dir, filename
            )

            return ModelReference(
                name=ref_item.name,
                type=ref_item.type,
                image_path=str(saved_path) if saved_path else "",
                prompt_used=prompt,
                created_at=now,
            )

        tasks = [_gen_single(item) for item in request.references]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 追加到已有 references
        existing_refs = metadata.get("references", [])
        new_refs: list[dict[str, Any]] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(
                    "参考图 %s 生成失败: %s",
                    request.references[i].name, str(res),
                )
            else:
                new_refs.append(res.model_dump(mode="json"))

        existing_refs.extend(new_refs)
        metadata["references"] = existing_refs
        metadata["updated_at"] = now
        self._save_model_metadata(model_dir, metadata)

        return self._metadata_to_response(metadata)

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------

    def list_models(
        self, limit: int = 50, offset: int = 0,
    ) -> list[ModelListItem]:
        """列出已保存的模特"""
        if not self._models_path.exists():
            return []

        items: list[ModelListItem] = []
        dirs = sorted(self._models_path.iterdir(), reverse=True)

        for model_dir in dirs:
            if not model_dir.is_dir():
                continue
            metadata = self._load_model_metadata(model_dir)
            if metadata is None:
                continue

            # 查找缩略图
            thumbnail = None
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                thumb_path = model_dir / f"thumbnail{ext}"
                if thumb_path.exists():
                    thumbnail = str(thumb_path)
                    break

            items.append(ModelListItem(
                model_id=metadata.get("model_id", model_dir.name),
                name=metadata.get("name", "未命名"),
                thumbnail=thumbnail,
                tags=metadata.get("tags", []),
                gender=metadata.get("gender", ""),
                style=metadata.get("style", ""),
                reference_count=len(metadata.get("references", [])),
                created_at=metadata.get("created_at"),
                updated_at=metadata.get("updated_at"),
            ))

        # 按创建时间排序
        items.sort(key=lambda x: x.created_at or "", reverse=True)

        return items[offset:offset + limit]

    def get_model(self, model_id: str) -> ModelCardResponse | None:
        """获取模特卡详情"""
        model_dir = self._models_path / model_id
        metadata = self._load_model_metadata(model_dir)
        if metadata is None:
            return None
        return self._metadata_to_response(metadata)

    def delete_model(self, model_id: str) -> bool:
        """删除模特"""
        model_dir = self._models_path / model_id
        if not model_dir.exists():
            return False
        shutil.rmtree(model_dir)
        logger.info("模特已删除: %s", model_id)
        return True

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata(
        model_id: str,
        name: str,
        description: str,
        tags: list[str] | None,
        gender: str,
        style: str,
        original_prompt: str | None,
        now: str,
        original_image: str | None = None,
        references: list[ModelReference] | None = None,
        status: str = "completed",
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "model_id": model_id,
            "name": name,
            "description": description,
            "tags": tags or [],
            "gender": gender,
            "style": style,
            "status": status,
            "original_image": original_image,
            "original_prompt": original_prompt,
            "references": [
                r.model_dump(mode="json") for r in (references or [])
            ],
            "created_at": now,
            "updated_at": now,
            "error": error,
        }

    def _save_model_metadata(
        self, model_dir: Path, metadata: dict[str, Any],
    ) -> None:
        meta_path = model_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _load_model_metadata(model_dir: Path) -> dict[str, Any] | None:
        meta_path = model_dir / "metadata.json"
        if not meta_path.exists():
            return None
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _metadata_to_response(metadata: dict[str, Any]) -> ModelCardResponse:
        refs = []
        for r in metadata.get("references", []):
            refs.append(ModelReference(
                name=r.get("name", ""),
                type=r.get("type", ReferenceType.VIEW),
                image_path=r.get("image_path", ""),
                prompt_used=r.get("prompt_used"),
                created_at=r.get("created_at"),
            ))

        status_str = metadata.get("status", "completed")
        try:
            status = TaskStatus(status_str)
        except ValueError:
            status = TaskStatus.COMPLETED

        return ModelCardResponse(
            model_id=metadata.get("model_id", ""),
            name=metadata.get("name", ""),
            description=metadata.get("description", ""),
            tags=metadata.get("tags", []),
            gender=metadata.get("gender", ""),
            style=metadata.get("style", ""),
            status=status,
            original_image_path=metadata.get("original_image"),
            references=refs,
            created_at=metadata.get("created_at"),
            updated_at=metadata.get("updated_at"),
            original_prompt=metadata.get("original_prompt"),
            error=metadata.get("error"),
        )
