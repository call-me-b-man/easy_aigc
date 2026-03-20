"""
模特生成 API 路由
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.schemas import (
    EnrichModelRequest,
    ModelCardResponse,
    ModelListItem,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/models", tags=["Models"])


# ---------- 依赖注入 (由 main.py 设置) ----------

_model_generator = None


def set_model_generator(generator):
    global _model_generator
    _model_generator = generator


def _get_generator():
    if _model_generator is None:
        raise HTTPException(500, "ModelGenerator 未初始化")
    return _model_generator


# ---------- 文生图创建模特 ----------

@router.post("/generate", response_model=ModelCardResponse)
async def generate_model(
    name: Annotated[str, Form(description="模特名称")],
    description: Annotated[str, Form(description="模特外观描述")] = "",
    tags: Annotated[str | None, Form(description="标签 JSON 数组")] = None,
    gender: Annotated[str, Form(description="性别: male/female")] = "female",
    style: Annotated[str, Form(description="风格描述")] = "时尚写真",
    custom_prompt: Annotated[str | None, Form(description="自定义文生图 Prompt")] = None,
    prompt_variables: Annotated[str | None, Form(description="模板变量 JSON")] = None,
    provider: Annotated[str | None, Form(description="指定 Provider")] = None,
    model: Annotated[str | None, Form(description="指定文生图模型")] = None,
    image_size: Annotated[str | None, Form(description="输出图片尺寸")] = None,
    views: Annotated[str | None, Form(description="视角列表 JSON 数组")] = None,
    multiview_provider: Annotated[str | None, Form(description="多视角 Provider")] = None,
    multiview_model: Annotated[str | None, Form(description="多视角模型")] = None,
):
    """
    文生图创建模特

    通过文字描述生成模特正面全身照，并自动生成多视角参考图。
    生成的模特卡将被持久化保存，可供后续复用和完善。
    """
    generator = _get_generator()

    parsed_tags = _parse_json_list(tags, "tags")
    parsed_views = _parse_json_list(views, "views")
    parsed_variables = _parse_json_dict(prompt_variables, "prompt_variables")

    result = await generator.create(
        name=name,
        description=description,
        tags=parsed_tags,
        gender=gender,
        style=style,
        custom_prompt=custom_prompt,
        prompt_variables=parsed_variables,
        provider_name=provider,
        model=model,
        image_size=image_size,
        views=parsed_views,
        multiview_provider=multiview_provider,
        multiview_model=multiview_model,
    )
    return result


# ---------- 从图片创建模特 ----------

@router.post("/generate-from-image", response_model=ModelCardResponse)
async def generate_model_from_image(
    image: UploadFile = File(..., description="模特图片"),
    name: Annotated[str, Form(description="模特名称")] = "",
    description: Annotated[str, Form(description="模特描述")] = "",
    tags: Annotated[str | None, Form(description="标签 JSON 数组")] = None,
    gender: Annotated[str, Form(description="性别")] = "female",
    style: Annotated[str, Form(description="风格")] = "时尚写真",
    views: Annotated[str | None, Form(description="视角列表 JSON")] = None,
    provider: Annotated[str | None, Form(description="Provider")] = None,
    model: Annotated[str | None, Form(description="模型")] = None,
    image_size: Annotated[str | None, Form(description="输出图片尺寸")] = None,
):
    """
    从已有图片创建模特

    上传模特图片，自动生成多视角参考图，创建模特卡。
    """
    generator = _get_generator()

    content = await image.read()
    if not content:
        raise HTTPException(400, "上传的图片为空")

    parsed_tags = _parse_json_list(tags, "tags")
    parsed_views = _parse_json_list(views, "views")

    result = await generator.create_from_image(
        image_content=content,
        image_filename=image.filename or "upload.png",
        name=name or (image.filename or "未命名模特"),
        description=description,
        tags=parsed_tags,
        gender=gender,
        style=style,
        views=parsed_views,
        provider_name=provider,
        model=model,
        image_size=image_size,
    )
    return result


# ---------- 图生图完善模特 ----------

@router.post("/{model_id}/enrich", response_model=ModelCardResponse)
async def enrich_model(
    model_id: str,
    references: Annotated[str, Form(
        description="要追加的参考图 JSON 数组，如 "
                    '[{"name":"walking_front","type":"pose"}]',
    )],
    prompt_variables: Annotated[str | None, Form(description="模板变量 JSON")] = None,
    provider: Annotated[str | None, Form(description="Provider")] = None,
    model: Annotated[str | None, Form(description="图生图模型")] = None,
    image_size: Annotated[str | None, Form(description="输出图片尺寸")] = None,
):
    """
    图生图完善模特 — 追加参考图

    基于已创建模特的原始图片，保持主体一致性，
    生成更多角度/姿势的参考图。可多次调用反复完善。
    """
    generator = _get_generator()

    # 解析 references JSON
    try:
        refs_data = json.loads(references)
    except json.JSONDecodeError:
        raise HTTPException(400, "references 必须是有效的 JSON 数组")

    parsed_variables = _parse_json_dict(prompt_variables, "prompt_variables")

    request = EnrichModelRequest(
        references=refs_data,
        prompt_variables=parsed_variables,
        provider=provider,
        model=model,
        image_size=image_size,
    )

    result = await generator.enrich(model_id, request)
    if result.error:
        raise HTTPException(404 if "不存在" in result.error else 400, result.error)
    return result


# ---------- 列出模特 ----------

@router.get("", response_model=list[ModelListItem])
async def list_models(
    limit: int = 50,
    offset: int = 0,
):
    """
    列出所有已保存的模特

    支持分页，按创建时间倒序排列。
    """
    generator = _get_generator()
    return generator.list_models(limit=limit, offset=offset)


# ---------- 模特详情 ----------

@router.get("/{model_id}", response_model=ModelCardResponse)
async def get_model(model_id: str):
    """获取模特卡详情"""
    generator = _get_generator()
    result = generator.get_model(model_id)
    if result is None:
        raise HTTPException(404, f"模特 {model_id} 不存在")
    return result


# ---------- 删除模特 ----------

@router.delete("/{model_id}")
async def delete_model(model_id: str):
    """删除模特及其所有参考图"""
    generator = _get_generator()
    success = generator.delete_model(model_id)
    if not success:
        raise HTTPException(404, f"模特 {model_id} 不存在")
    return {"message": f"模特 {model_id} 已删除"}


# ---------- 工具函数 ----------

def _parse_json_list(val: str | None, name: str) -> list | None:
    if val is None:
        return None
    try:
        result = json.loads(val)
        if not isinstance(result, list):
            raise HTTPException(400, f"{name} 必须是 JSON 数组")
        return result
    except json.JSONDecodeError:
        raise HTTPException(400, f"{name} 必须是有效的 JSON 数组")


def _parse_json_dict(val: str | None, name: str) -> dict | None:
    if val is None:
        return None
    try:
        result = json.loads(val)
        if not isinstance(result, dict):
            raise HTTPException(400, f"{name} 必须是 JSON 对象")
        return result
    except json.JSONDecodeError:
        raise HTTPException(400, f"{name} 必须是有效的 JSON 对象")
