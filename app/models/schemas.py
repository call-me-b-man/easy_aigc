"""
数据模型 — Pydantic 请求/响应模型
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------- 枚举 ----------

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------- 请求模型 ----------

class ExtractSubjectRequest(BaseModel):
    """主体提取请求"""
    provider: str | None = Field(None, description="指定 Provider，为空用默认")
    model: str | None = Field(None, description="指定模型，为空用默认")
    custom_prompt: str | None = Field(None, description="完全自定义 Prompt（覆盖模板）")
    prompt_variables: dict[str, str] | None = Field(
        None,
        description="模板变量注入，如 {subject_type: '卡通角色'}",
    )
    image_size: str | None = Field(None, description="输出图片尺寸，如 '1024x1024'")


class MultiViewRequest(BaseModel):
    """多视角生成请求"""
    subject_image_path: str | None = Field(
        None,
        description="主体图片路径（若来自提取结果）",
    )
    views: list[str] | None = Field(None, description="指定视角列表，为空用默认")
    provider: str | None = Field(None, description="指定 Provider")
    model: str | None = Field(None, description="指定模型")
    custom_prompts: dict[str, str] | None = Field(
        None,
        description="按视角自定义 Prompt，如 {front: '...'}",
    )
    prompt_variables: dict[str, str] | None = Field(
        None,
        description="全局模板变量注入",
    )
    image_size: str | None = Field(None, description="输出图片尺寸")


class PipelineRequest(BaseModel):
    """完整流水线请求（主体提取 + 多视角生成）"""
    # 提取阶段配置
    extract_provider: str | None = Field(None, description="提取阶段 Provider")
    extract_model: str | None = Field(None, description="提取阶段模型")
    extract_custom_prompt: str | None = Field(None, description="提取阶段自定义 Prompt")
    extract_prompt_variables: dict[str, str] | None = Field(
        None,
        description="提取阶段模板变量",
    )

    # 多视角阶段配置
    views: list[str] | None = Field(None, description="生成视角列表")
    multiview_provider: str | None = Field(None, description="多视角阶段 Provider")
    multiview_model: str | None = Field(None, description="多视角阶段模型")
    multiview_custom_prompts: dict[str, str] | None = Field(
        None,
        description="按视角自定义 Prompt",
    )
    multiview_prompt_variables: dict[str, str] | None = Field(
        None,
        description="多视角阶段模板变量",
    )
    image_size: str | None = Field(None, description="输出图片尺寸")


# ---------- 响应模型 ----------

class ExtractSubjectResponse(BaseModel):
    """主体提取响应"""
    task_id: str
    status: TaskStatus
    subject_image_path: str | None = None
    prompt_used: str | None = None
    provider_used: str | None = None
    model_used: str | None = None
    error: str | None = None


class ViewResult(BaseModel):
    """单个视角结果"""
    view_name: str
    image_path: str | None = None
    prompt_used: str | None = None
    status: TaskStatus = TaskStatus.PENDING


class MultiViewResponse(BaseModel):
    """多视角生成响应"""
    task_id: str
    status: TaskStatus
    views: list[ViewResult] = Field(default_factory=list)
    provider_used: str | None = None
    model_used: str | None = None
    error: str | None = None


class PipelineResponse(BaseModel):
    """完整流水线响应"""
    task_id: str
    status: TaskStatus
    subject_image_path: str | None = None
    views: list[ViewResult] = Field(default_factory=list)
    extract_prompt_used: str | None = None
    provider_used: str | None = None
    model_used: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskStatusResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str
    status: TaskStatus
    result: dict[str, Any] | None = None
    error: str | None = None


# ---------- 配置相关模型 ----------

class ConfigResponse(BaseModel):
    """配置查询响应"""
    default_provider: str
    providers: dict[str, Any]
    subject_extraction_model: str
    multiview_generation_model: str
    output_base_path: str
    default_views: list[str]
    num_inference_steps: int
    cfg_scale: float
    prompts: dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    """配置更新请求（部分更新）"""
    default_provider: str | None = None
    providers: dict[str, Any] | None = None
    subject_extraction_model: str | None = None
    multiview_generation_model: str | None = None
    output_base_path: str | None = None
    default_views: list[str] | None = None
    num_inference_steps: int | None = None
    cfg_scale: float | None = None


class PromptUpdateRequest(BaseModel):
    """Prompt 模板更新请求"""
    subject_extraction: str | None = None
    multiview: dict[str, str] | None = None


class ProviderInfo(BaseModel):
    """Provider 信息"""
    name: str
    enabled: bool
    base_url: str
    models: list[ModelInfo] = Field(default_factory=list)


class ModelInfo(BaseModel):
    """模型信息"""
    id: str
    name: str
    capabilities: list[str] = Field(default_factory=list)
    provider: str


# ---------- 模特生成相关模型 ----------

class ReferenceType(str, Enum):
    """参考图类型"""
    VIEW = "view"      # 视角参考图
    POSE = "pose"      # 姿势参考图


class CreateModelRequest(BaseModel):
    """文生图创建模特请求"""
    name: str = Field(..., description="模特名称")
    description: str = Field("", description="模特外观描述（用于文生图 Prompt）")
    tags: list[str] = Field(default_factory=list, description="标签，如 ['时尚', '都市']")
    gender: str = Field("female", description="性别: male/female")
    style: str = Field("时尚写真", description="风格描述")

    # 生成配置
    custom_prompt: str | None = Field(None, description="完全自定义文生图 Prompt（覆盖模板）")
    prompt_variables: dict[str, str] | None = Field(
        None,
        description="模板变量注入",
    )
    provider: str | None = Field(None, description="指定 Provider")
    model: str | None = Field(None, description="指定文生图模型")
    image_size: str | None = Field(None, description="输出图片尺寸")

    # 视角配置
    views: list[str] | None = Field(
        None,
        description="创建时自动生成的视角列表，为空用默认",
    )
    multiview_provider: str | None = Field(None, description="多视角阶段 Provider")
    multiview_model: str | None = Field(None, description="多视角阶段模型")


class CreateModelFromImageRequest(BaseModel):
    """从已有图片创建模特请求"""
    name: str = Field(..., description="模特名称")
    description: str = Field("", description="模特描述")
    tags: list[str] = Field(default_factory=list, description="标签")
    gender: str = Field("female", description="性别")
    style: str = Field("时尚写真", description="风格")

    # 多视角配置
    views: list[str] | None = Field(None, description="自动生成的视角列表")
    provider: str | None = Field(None, description="多视角 Provider")
    model: str | None = Field(None, description="多视角模型")
    image_size: str | None = Field(None, description="输出图片尺寸")


class EnrichReferenceItem(BaseModel):
    """单条追加参考图配置"""
    name: str = Field(..., description="参考图名称，如 'walking_front', 'three_quarter'")
    type: ReferenceType = Field(ReferenceType.POSE, description="类型: view 或 pose")
    custom_prompt: str | None = Field(
        None,
        description="该参考图的自定义 Prompt",
    )


class EnrichModelRequest(BaseModel):
    """图生图追加参考图请求（完善模特）"""
    references: list[EnrichReferenceItem] = Field(
        ...,
        description="要追加的参考图列表",
    )
    prompt_variables: dict[str, str] | None = Field(
        None,
        description="全局模板变量注入",
    )
    provider: str | None = Field(None, description="指定 Provider")
    model: str | None = Field(None, description="指定图生图模型")
    image_size: str | None = Field(None, description="输出图片尺寸")


class ModelReference(BaseModel):
    """模特卡中的单张参考图信息"""
    name: str
    type: ReferenceType
    image_path: str
    prompt_used: str | None = None
    created_at: str | None = None


class ModelCardResponse(BaseModel):
    """模特卡完整响应"""
    model_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    gender: str = ""
    style: str = ""
    status: TaskStatus = TaskStatus.COMPLETED
    original_image_path: str | None = None
    references: list[ModelReference] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    original_prompt: str | None = None
    error: str | None = None


class ModelListItem(BaseModel):
    """模特列表精简项"""
    model_id: str
    name: str
    thumbnail: str | None = None
    tags: list[str] = Field(default_factory=list)
    gender: str = ""
    style: str = ""
    reference_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
