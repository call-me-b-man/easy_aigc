"""
配置管理 API 路由
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.config import get_settings, update_settings
from app.models.schemas import (
    ConfigResponse,
    ConfigUpdateRequest,
    ModelInfo,
    PromptUpdateRequest,
    ProviderInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/config", tags=["Config"])

# Provider Registry 引用 (由 main.py 设置)
_registry = None


def set_registry(registry):
    global _registry
    _registry = registry


# ---------- 配置查询 ----------

@router.get("", response_model=ConfigResponse)
async def get_config():
    """获取当前配置（含 Prompt 模板）"""
    settings = get_settings()
    return ConfigResponse(
        default_provider=settings.default_provider,
        providers={
            name: {
                "base_url": cfg.base_url,
                "enabled": cfg.enabled,
                "has_api_key": bool(cfg.api_key),
            }
            for name, cfg in settings.providers.items()
        },
        subject_extraction_model=settings.subject_extraction_model,
        multiview_generation_model=settings.multiview_generation_model,
        output_base_path=settings.output_base_path,
        default_views=settings.default_views,
        num_inference_steps=settings.num_inference_steps,
        cfg_scale=settings.cfg_scale,
        prompts=settings.prompts.model_dump(),
    )


# ---------- 配置更新 ----------

@router.put("", response_model=ConfigResponse)
async def update_config(req: ConfigUpdateRequest):
    """
    更新配置并持久化到 YAML 文件

    只需传入要修改的字段，其余保持不变。
    """
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "没有需要更新的字段")

    try:
        new_settings = update_settings(updates)
        logger.info("配置已更新: %s", list(updates.keys()))
    except Exception as e:
        raise HTTPException(500, f"配置更新失败: {str(e)}")

    return ConfigResponse(
        default_provider=new_settings.default_provider,
        providers={
            name: {
                "base_url": cfg.base_url,
                "enabled": cfg.enabled,
                "has_api_key": bool(cfg.api_key),
            }
            for name, cfg in new_settings.providers.items()
        },
        subject_extraction_model=new_settings.subject_extraction_model,
        multiview_generation_model=new_settings.multiview_generation_model,
        output_base_path=new_settings.output_base_path,
        default_views=new_settings.default_views,
        num_inference_steps=new_settings.num_inference_steps,
        cfg_scale=new_settings.cfg_scale,
        prompts=new_settings.prompts.model_dump(),
    )


# ---------- Prompt 模板更新 ----------

@router.put("/prompts")
async def update_prompts(req: PromptUpdateRequest):
    """
    单独更新 Prompt 模板并持久化

    支持部分更新: 只传 subject_extraction 或只传 multiview 都可以。
    """
    updates: dict = {}
    if req.subject_extraction is not None:
        updates["subject_extraction"] = req.subject_extraction
    if req.multiview is not None:
        updates["multiview"] = req.multiview

    if not updates:
        raise HTTPException(400, "没有需要更新的 Prompt 模板")

    new_settings = update_settings({"prompts": updates})

    # 同步更新 PromptEngine (通过重新加载)
    logger.info("Prompt 模板已更新: %s", list(updates.keys()))

    return {
        "message": "Prompt 模板已更新并持久化",
        "prompts": new_settings.prompts.model_dump(),
    }


# ---------- Provider 列表 ----------

@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers():
    """列出所有可用 Provider 及其支持的模型"""
    settings = get_settings()
    result: list[ProviderInfo] = []

    if _registry:
        for name, provider in _registry.list_all().items():
            cfg = settings.providers.get(name)
            models = [
                ModelInfo(**m.model_dump()) if hasattr(m, "model_dump") else m
                for m in provider.list_models()
            ]
            result.append(ProviderInfo(
                name=name,
                enabled=cfg.enabled if cfg else True,
                base_url=cfg.base_url if cfg else "",
                models=models,
            ))
    else:
        # Registry 不可用时从配置返回基本信息
        for name, cfg in settings.providers.items():
            result.append(ProviderInfo(
                name=name,
                enabled=cfg.enabled,
                base_url=cfg.base_url,
            ))

    return result
