"""
分镜脚本生成服务 — 图片识别 + 剧本/分镜设计

流程:
  1. 接收多张图片 (上传文件 / 项目内部路径 / base64)
  2. 将图片按索引编号，组装成 VLM 多模态 messages
  3. 调用 ChatProvider (SiliconFlow Qwen-VL) 进行识图 + 分镜生成
  4. 解析 JSON 结果，返回结构化 StoryboardResponse
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models.schemas import (
    StoryboardResponse,
    StoryboardScene,
    TaskStatus,
)
from app.providers.base import ChatProvider
from app.providers.registry import ProviderRegistry
from app.services.prompt_engine import PromptEngine
from app.utils.image_utils import image_to_base64, is_base64
from app.utils.storage import StorageManager

logger = logging.getLogger(__name__)


class StoryboardGenerator:
    """
    分镜脚本生成器

    负责将输入图片通过 VLM 识图后，由大模型生成结构化剧本与分镜。
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
        image_data_list: list[str],
        custom_prompt: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> StoryboardResponse:
        """
        生成分镜脚本

        Args:
            image_data_list: 图片列表，每项可以是:
                - 项目内部相对路径 (如 "output/2026-03-23/.../subject.png")
                - data:image/...;base64,... 格式
                - 绝对路径
            custom_prompt: 用户附加提示词
            provider_name: 指定 Provider
            model: 指定 VLM 模型
            temperature: 采样温度
            max_tokens: 最大生成 token 数

        Returns:
            StoryboardResponse
        """
        task_id = uuid.uuid4().hex[:12]
        settings = get_settings()
        actual_model = model or settings.storyboard_model

        try:
            # 1. 获取 ChatProvider
            chat_provider = self._get_chat_provider(provider_name)

            # 2. 将图片全部转为 base64 data URI
            image_b64_list = self._resolve_images(image_data_list)
            logger.info(
                "分镜生成开始: task_id=%s, 图片数=%d, model=%s",
                task_id, len(image_b64_list), actual_model,
            )

            # 3. 构建 VLM messages
            messages = self._build_messages(
                image_b64_list, custom_prompt,
            )

            # 4. 调用 ChatProvider
            chat_result = await chat_provider.chat_completion(
                messages=messages,
                model=actual_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # 5. 解析 JSON 响应
            parsed = self._parse_response(chat_result.content)

            # 6. 构建结构化响应
            scenes = []
            for s in parsed.get("scenes", []):
                scenes.append(StoryboardScene(
                    scene_number=s.get("scene_number", 0),
                    image_index=s.get("image_index", 0),
                    scene_description=s.get("scene_description", ""),
                    camera_movement=s.get("camera_movement", ""),
                    dialogue=s.get("dialogue", ""),
                    duration=s.get("duration", ""),
                    notes=s.get("notes", ""),
                ))

            response = StoryboardResponse(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                script_title=parsed.get("script_title", ""),
                script_summary=parsed.get("script_summary", ""),
                scenes=scenes,
                image_descriptions=parsed.get("image_descriptions", []),
                model_used=chat_result.model_used,
                provider_used=chat_result.provider_name,
            )

            # 7. 持久化结果
            await self._save_result(task_id, response, chat_result.content)

            logger.info("分镜生成完成: task_id=%s, 场景数=%d", task_id, len(scenes))
            return response

        except Exception as e:
            logger.error("分镜生成失败: task_id=%s, error=%s", task_id, str(e))
            return StoryboardResponse(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
            )

    def _get_chat_provider(self, provider_name: str | None) -> ChatProvider:
        """获取支持 ChatProvider 接口的 Provider"""
        settings = get_settings()
        name = provider_name or settings.default_provider
        provider = self._registry.get(name)
        if provider is None:
            raise RuntimeError(f"Provider '{name}' 未注册")
        if not isinstance(provider, ChatProvider):
            raise RuntimeError(
                f"Provider '{name}' 不支持聊天/识图功能 (未实现 ChatProvider)"
            )
        return provider

    def _resolve_images(self, image_data_list: list[str]) -> list[str]:
        """
        将各种格式的图片输入统一转换为 data URI (base64)

        支持:
        - 项目内部相对路径 → 读取文件 → base64
        - 绝对路径 → 读取文件 → base64
        - 已经是 base64 → 直接使用
        """
        result: list[str] = []
        project_root = Path(__file__).resolve().parent.parent

        for item in image_data_list:
            if is_base64(item):
                result.append(item)
            else:
                # 尝试作为路径解析
                path = Path(item)
                if not path.is_absolute():
                    path = project_root / item
                if path.exists():
                    result.append(image_to_base64(path))
                else:
                    raise FileNotFoundError(f"图片路径不存在: {item}")

        return result

    def _build_messages(
        self,
        image_b64_list: list[str],
        custom_prompt: str | None,
    ) -> list[dict[str, Any]]:
        """
        构建 OpenAI Vision 兼容的 messages 数组

        System Prompt 使用配置中的分镜模板，
        User Message 包含所有图片 (带索引标注) + 可选用户附加提示。
        """
        settings = get_settings()

        # System prompt
        extra_req = custom_prompt or ""
        system_text = settings.prompts.storyboard_system.format(
            extra_requirements=extra_req,
        )

        # User message: 文本说明 + 多张图片
        user_content: list[dict[str, Any]] = []

        # 文字部分: 告知图片数量和索引
        intro_text = f"以下是 {len(image_b64_list)} 张参考图片，索引从 0 开始。请仔细识别每张图片内容，然后设计剧本和分镜。"
        if custom_prompt:
            intro_text += f"\n\n用户特别要求: {custom_prompt}"

        user_content.append({"type": "text", "text": intro_text})

        # 图片部分
        for idx, b64 in enumerate(image_b64_list):
            user_content.append({
                "type": "text",
                "text": f"--- 图片 #{idx} ---",
            })
            user_content.append({
                "type": "image_url",
                "image_url": {"url": b64},
            })

        return [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_content},
        ]

    def _parse_response(self, raw_content: str) -> dict[str, Any]:
        """
        解析 LLM 返回的 JSON 字符串

        处理可能包裹在 ```json ... ``` 中的情况
        """
        cleaned = raw_content.strip()

        # 去掉 markdown 代码块标记
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(
                "JSON 解析失败, 尝试提取部分内容: %s\n原始内容:\n%s",
                str(e), raw_content[:500],
            )
            # 尝试找到第一个 { 和最后一个 }
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    pass

            raise RuntimeError(
                f"无法解析模型返回的 JSON: {raw_content[:300]}"
            ) from e

    async def _save_result(
        self,
        task_id: str,
        response: StoryboardResponse,
        raw_llm_output: str,
    ) -> None:
        """持久化分镜生成结果"""
        try:
            task_dir = self._storage.get_task_dir(task_id)

            # 保存结构化结果
            result_path = task_dir / "storyboard.json"
            result_path.write_text(
                response.model_dump_json(indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # 保存原始 LLM 输出
            raw_path = task_dir / "raw_llm_output.txt"
            raw_path.write_text(raw_llm_output, encoding="utf-8")

            # 保存元数据
            self._storage.save_metadata(task_dir, {
                "task_id": task_id,
                "type": "storyboard",
                "status": response.status.value,
                "provider": response.provider_used or "",
                "model": response.model_used or "",
                "script_title": response.script_title,
                "scene_count": len(response.scenes),
                "created_at": datetime.now().isoformat(),
            })

            logger.info("分镜结果已保存: %s", task_dir)
        except Exception as e:
            logger.warning("保存分镜结果失败: %s", str(e))
