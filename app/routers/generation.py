"""
图片生成 API 路由
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.models.schemas import (
    ExtractSubjectResponse,
    MultiViewResponse,
    PipelineResponse,
    TaskStatus,
    ViewResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/generation", tags=["Generation"])


# ---------- 依赖注入 (由 main.py 设置) ----------

_extractor = None
_multiview = None


def set_services(extractor, multiview):
    global _extractor, _multiview
    _extractor = extractor
    _multiview = multiview


def _get_extractor():
    if _extractor is None:
        raise HTTPException(500, "SubjectExtractor 未初始化")
    return _extractor


def _get_multiview():
    if _multiview is None:
        raise HTTPException(500, "MultiViewGenerator 未初始化")
    return _multiview


# ---------- 主体提取 ----------

@router.post("/extract-subject", response_model=ExtractSubjectResponse)
async def extract_subject(
    image: UploadFile = File(..., description="上传图片"),
    provider: Annotated[str | None, Form()] = None,
    model: Annotated[str | None, Form()] = None,
    custom_prompt: Annotated[str | None, Form()] = None,
    prompt_variables: Annotated[str | None, Form()] = None,
    image_size: Annotated[str | None, Form()] = None,
):
    """
    主体提取接口

    上传一张图片，提取其中的主体（去除背景）。

    - **provider**: 指定 Provider (siliconflow/evolink)，为空用默认
    - **model**: 指定模型，为空用配置默认
    - **custom_prompt**: 完全自定义 Prompt，覆盖模板
    - **prompt_variables**: JSON 格式的模板变量，如 {"subject_type": "卡通角色"}
    - **image_size**: 输出尺寸，如 "1024x1024"
    """
    extractor = _get_extractor()

    # 解析 prompt_variables JSON
    variables = None
    if prompt_variables:
        try:
            variables = json.loads(prompt_variables)
        except json.JSONDecodeError:
            raise HTTPException(400, "prompt_variables 必须是有效的 JSON 字符串")

    # 读取上传的图片
    content = await image.read()
    if not content:
        raise HTTPException(400, "上传的图片为空")

    result = await extractor.extract(
        image_content=content,
        image_filename=image.filename or "upload.png",
        provider_name=provider,
        model=model,
        custom_prompt=custom_prompt,
        prompt_variables=variables,
        image_size=image_size,
    )
    return result


# ---------- 多视角生成 ----------

@router.post("/multi-view", response_model=MultiViewResponse)
async def generate_multi_view(
    image: UploadFile = File(..., description="主体图片"),
    views: Annotated[str | None, Form()] = None,
    provider: Annotated[str | None, Form()] = None,
    model: Annotated[str | None, Form()] = None,
    custom_prompts: Annotated[str | None, Form()] = None,
    prompt_variables: Annotated[str | None, Form()] = None,
    image_size: Annotated[str | None, Form()] = None,
):
    """
    多视角生成接口

    上传主体图片，生成多个视角的一致性图片。

    - **views**: JSON 数组, 如 ["front","back","left_side"]，为空用默认
    - **custom_prompts**: JSON 对象, 按视角自定义 Prompt, 如 {"front":"..."}
    - **prompt_variables**: JSON 对象, 全局模板变量
    """
    multiview = _get_multiview()

    # 解析 JSON 参数
    parsed_views = None
    if views:
        try:
            parsed_views = json.loads(views)
        except json.JSONDecodeError:
            raise HTTPException(400, "views 必须是有效的 JSON 数组")

    parsed_custom_prompts = None
    if custom_prompts:
        try:
            parsed_custom_prompts = json.loads(custom_prompts)
        except json.JSONDecodeError:
            raise HTTPException(400, "custom_prompts 必须是有效的 JSON 对象")

    parsed_variables = None
    if prompt_variables:
        try:
            parsed_variables = json.loads(prompt_variables)
        except json.JSONDecodeError:
            raise HTTPException(400, "prompt_variables 必须是有效的 JSON 字符串")

    # 保存上传的主体图片到临时位置
    content = await image.read()
    if not content:
        raise HTTPException(400, "上传的图片为空")

    import tempfile, os
    ext = os.path.splitext(image.filename or "img.png")[1] or ".png"
    with tempfile.NamedTemporaryFile(
        suffix=ext, delete=False, dir=None
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await multiview.generate(
            subject_image_path=tmp_path,
            views=parsed_views,
            provider_name=provider,
            model=model,
            custom_prompts=parsed_custom_prompts,
            prompt_variables=parsed_variables,
            image_size=image_size,
        )
        return result
    finally:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------- 完整流水线 ----------

@router.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline(
    image: UploadFile = File(..., description="原始图片"),
    # 提取阶段
    extract_provider: Annotated[str | None, Form()] = None,
    extract_model: Annotated[str | None, Form()] = None,
    extract_custom_prompt: Annotated[str | None, Form()] = None,
    extract_prompt_variables: Annotated[str | None, Form()] = None,
    # 多视角阶段
    views: Annotated[str | None, Form()] = None,
    multiview_provider: Annotated[str | None, Form()] = None,
    multiview_model: Annotated[str | None, Form()] = None,
    multiview_custom_prompts: Annotated[str | None, Form()] = None,
    multiview_prompt_variables: Annotated[str | None, Form()] = None,
    image_size: Annotated[str | None, Form()] = None,
):
    """
    完整流水线接口

    一步完成: 上传图片 → 主体提取 → 多视角生成

    提取和多视角阶段可分别配置 Provider、Model 和 Prompt。
    """
    extractor = _get_extractor()
    multiview = _get_multiview()

    content = await image.read()
    if not content:
        raise HTTPException(400, "上传的图片为空")

    # 解析 JSON 参数
    def _parse_json(val: str | None) -> dict | list | None:
        if val is None:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            raise HTTPException(400, f"JSON 解析失败: {val[:50]}")

    extract_vars = _parse_json(extract_prompt_variables)
    mv_views = _parse_json(views)
    mv_custom = _parse_json(multiview_custom_prompts)
    mv_vars = _parse_json(multiview_prompt_variables)

    # 步骤1: 主体提取
    extract_result = await extractor.extract(
        image_content=content,
        image_filename=image.filename or "upload.png",
        provider_name=extract_provider,
        model=extract_model,
        custom_prompt=extract_custom_prompt,
        prompt_variables=extract_vars,
        image_size=image_size,
    )

    if (
        extract_result.status != TaskStatus.COMPLETED
        or not extract_result.subject_image_path
    ):
        return PipelineResponse(
            task_id=extract_result.task_id,
            status=TaskStatus.FAILED,
            extract_prompt_used=extract_result.prompt_used,
            provider_used=extract_result.provider_used,
            model_used=extract_result.model_used,
            metadata={"error": "主体提取失败"},
        )

    # 步骤2: 多视角生成
    mv_result = await multiview.generate(
        subject_image_path=extract_result.subject_image_path,
        views=mv_views,
        provider_name=multiview_provider,
        model=multiview_model,
        custom_prompts=mv_custom,
        prompt_variables=mv_vars,
        image_size=image_size,
        task_id=extract_result.task_id,
    )

    return PipelineResponse(
        task_id=extract_result.task_id,
        status=mv_result.status,
        subject_image_path=extract_result.subject_image_path,
        views=mv_result.views,
        extract_prompt_used=extract_result.prompt_used,
        provider_used=f"extract:{extract_result.provider_used}, "
                      f"multiview:{mv_result.provider_used}",
        model_used=f"extract:{extract_result.model_used}, "
                   f"multiview:{mv_result.model_used}",
    )


# ---------- 历史记录 ----------

@router.get("/history")
async def list_history(limit: int = 20):
    """
    获取最近的生成记录列表

    扫描 output 目录中的 metadata.json，按时间倒序返回。
    """
    from pathlib import Path
    from app.config import get_settings

    settings = get_settings()
    output_dir = Path(settings.output_base_path)

    if not output_dir.exists():
        return []

    records = []
    for date_dir in sorted(output_dir.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        for task_dir in sorted(date_dir.iterdir(), reverse=True):
            if not task_dir.is_dir():
                continue
            meta_path = task_dir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                images = [
                    f.name for f in task_dir.iterdir()
                    if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
                ]
                records.append({
                    "task_id": meta.get("task_id", task_dir.name),
                    "type": meta.get("type", "unknown"),
                    "status": meta.get("status", ""),
                    "provider": meta.get("provider", ""),
                    "model": meta.get("model", ""),
                    "prompt_used": meta.get("prompt_used", ""),
                    "date": date_dir.name,
                    "images": images,
                    "dir": f"{date_dir.name}/{task_dir.name}",
                    "mtime": meta_path.stat().st_mtime,
                })
            except Exception:
                continue
        if len(records) >= limit:
            break

    records.sort(key=lambda r: r.get("mtime", 0), reverse=True)
    return records[:limit]
