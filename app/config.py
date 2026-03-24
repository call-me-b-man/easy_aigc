"""
配置管理模块

配置优先级: 请求体参数 > 环境变量 > YAML 文件 > 默认值
支持通过 API 修改配置并持久化到 YAML 文件
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------- 子配置模型 ----------

class ProviderConfig(BaseModel):
    """单个提供商的配置"""
    api_key: str = ""
    base_url: str = ""
    enabled: bool = True


class PromptTemplates(BaseModel):
    """Prompt 模板配置 — 支持 Python str.format() 语法变量"""

    subject_extraction: str = (
        "Extract the main subject from this image. "
        "Remove the background completely. "
        "Keep only the primary {subject_type} on a clean white background. "
        "Maintain all original details and proportions."
    )

    multiview: dict[str, str] = Field(default_factory=lambda: {
        "front": (
            "Front view of {subject_description}. "
            "Maintain exact same appearance, colors, textures and details as the reference. "
            "Clean white background. {extra_requirements}"
        ),
        "left_side": (
            "Left side view of {subject_description}. "
            "Maintain exact same appearance, colors, textures and details as the reference. "
            "Clean white background. {extra_requirements}"
        ),
        "right_side": (
            "Right side view of {subject_description}. "
            "Maintain exact same appearance, colors, textures and details as the reference. "
            "Clean white background. {extra_requirements}"
        ),
        "back": (
            "Back view of {subject_description}. "
            "Maintain exact same appearance, colors, textures and details as the reference. "
            "Clean white background. {extra_requirements}"
        ),
        "top": (
            "Top-down view of {subject_description}. "
            "Maintain exact same appearance, colors, textures and details as the reference. "
            "Clean white background. {extra_requirements}"
        ),
    })

    # 模特生成 — 文生图 Prompt 模板
    model_generation: str = (
        "A full-body photo of a {gender} fashion model, {model_description}. "
        "Standing in a natural pose, facing the camera. "
        "Clean white background, studio lighting, high quality, "
        "fashion photography style. {extra_requirements}"
    )

    # 模特姿势参考图 — 图生图 Prompt 模板
    model_pose: dict[str, str] = Field(default_factory=lambda: {
        "walking_front": (
            "{model_description}, walking towards camera, natural stride, "
            "maintain exact same appearance and outfit as reference. "
            "Clean white background. {extra_requirements}"
        ),
        "sitting": (
            "{model_description}, sitting on a stool, relaxed pose, "
            "maintain exact same appearance and outfit as reference. "
            "Clean white background. {extra_requirements}"
        ),
        "hands_on_hips": (
            "{model_description}, standing with hands on hips, confident pose, "
            "maintain exact same appearance and outfit as reference. "
            "Clean white background. {extra_requirements}"
        ),
        "three_quarter": (
            "Three-quarter view of {model_description}, slight angle, "
            "maintain exact same appearance and outfit as reference. "
            "Clean white background. {extra_requirements}"
        ),
    })

    # 分镜脚本生成 — VLM System Prompt 模板
    storyboard_system: str = (
        "你是一个专业的分镜脚本设计师。\n"
        "你会收到一组图片，每张图片带有索引编号 (0-based)。\n"
        "你的任务是：\n"
        "1. 先仔细观察每张图片，识别其中的场景、人物、物体、色彩、情绪等细节。\n"
        "2. 基于这些图片设计一个连贯的剧本故事。\n"
        "3. 为每张图片设计对应的分镜，包含运镜、对白、时长等。\n\n"
        "你必须以以下 JSON 格式返回，不要返回任何其他内容：\n"
        '{{\n'
        '  "script_title": "剧本标题",\n'
        '  "script_summary": "剧本概要描述",\n'
        '  "image_descriptions": ["图0的识别描述", "图1的识别描述", ...],\n'
        '  "scenes": [\n'
        '    {{\n'
        '      "scene_number": 1,\n'
        '      "image_index": 0,\n'
        '      "scene_description": "画面描述",\n'
        '      "camera_movement": "运镜设计",\n'
        '      "dialogue": "对白或旁白",\n'
        '      "duration": "预估时长如 3s",\n'
        '      "notes": "导演备注"\n'
        '    }}\n'
        '  ]\n'
        '}}\n'
        "{extra_requirements}"
    )


# ---------- 主配置 ----------

def _get_config_dir() -> Path:
    """获取配置文件目录（项目根目录下的 config/）"""
    return Path(__file__).resolve().parent.parent / "config"


def _get_yaml_path() -> Path:
    return _get_config_dir() / "settings.yaml"


def _load_yaml_settings() -> dict[str, Any]:
    """从 YAML 文件加载配置"""
    yaml_path = _get_yaml_path()
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    return {}


class Settings(BaseSettings):
    """
    应用主配置

    加载顺序:
    1. 环境变量 (SILICONFLOW_API_KEY 等)
    2. config/settings.yaml
    3. 下方声明的默认值
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Provider 配置
    providers: dict[str, ProviderConfig] = Field(default_factory=lambda: {
        "siliconflow": ProviderConfig(
            base_url="https://api.siliconflow.cn/v1",
        ),
        "evolink": ProviderConfig(
            base_url="https://api.evolink.ai/v1",
        ),
    })
    default_provider: str = "siliconflow"

    # 模型配置
    subject_extraction_model: str = "Qwen/Qwen-Image-Edit-2509"
    multiview_generation_model: str = "Qwen/Qwen-Image-Edit-2509"
    model_generation_model: str = "Kwai-Kolors/Kolors"  # 文生图创建模特
    storyboard_model: str = "Qwen/Qwen2.5-VL-72B-Instruct"  # 分镜脚本 VLM 模型

    # Prompt 模板
    prompts: PromptTemplates = Field(default_factory=PromptTemplates)

    # 存储 & 生成参数
    output_base_path: str = "./output"
    models_base_path: str = "./output/models"  # 模特持久化目录
    default_views: list[str] = Field(
        default_factory=lambda: ["front", "left_side", "right_side", "back", "top"]
    )
    num_inference_steps: int = 50
    cfg_scale: float = 4.0

    @classmethod
    def load(cls) -> "Settings":
        """从 YAML + 环境变量加载配置"""
        yaml_data = _load_yaml_settings()

        # 环境变量覆盖 provider api_key
        siliconflow_key = os.getenv("SILICONFLOW_API_KEY", "")
        evolink_key = os.getenv("EVOLINK_API_KEY", "")

        if siliconflow_key:
            yaml_data.setdefault("providers", {}).setdefault("siliconflow", {})
            yaml_data["providers"]["siliconflow"]["api_key"] = siliconflow_key
        if evolink_key:
            yaml_data.setdefault("providers", {}).setdefault("evolink", {})
            yaml_data["providers"]["evolink"]["api_key"] = evolink_key

        return cls(**yaml_data)

    def save(self) -> None:
        """将当前配置持久化到 YAML 文件"""
        yaml_path = _get_yaml_path()
        yaml_path.parent.mkdir(parents=True, exist_ok=True)

        data = self.model_dump(mode="json")

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    def update_from_dict(self, updates: dict[str, Any]) -> "Settings":
        """
        从字典部分更新配置并持久化

        Returns:
            更新后的新 Settings 实例
        """
        current = self.model_dump(mode="json")
        _deep_merge(current, updates)
        new_settings = Settings(**current)
        new_settings.save()
        return new_settings


def _deep_merge(base: dict, override: dict) -> None:
    """递归合并字典，override 覆盖 base"""
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# ---------- 全局单例 ----------

_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例"""
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings


def reload_settings() -> Settings:
    """重新加载配置"""
    global _settings
    _settings = Settings.load()
    return _settings


def update_settings(updates: dict[str, Any]) -> Settings:
    """更新全局配置并持久化"""
    global _settings
    current = get_settings()
    _settings = current.update_from_dict(updates)
    return _settings
