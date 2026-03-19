"""
Prompt 模板引擎 — 负责模板解析与变量注入

支持三层优先级:
1. custom_prompt (请求级完全覆盖)
2. prompt_variables (注入模板变量)
3. YAML 配置中的默认模板
"""

from __future__ import annotations

import logging
import string

from app.config import PromptTemplates

logger = logging.getLogger(__name__)


class PromptEngine:
    """
    Prompt 模板引擎

    使用 Python str.format() 语法:
    - {subject_type}           → 主体类型
    - {subject_description}    → 主体描述
    - {view_direction}         → 视角方向
    - {extra_requirements}     → 额外要求
    """

    # 多视角未匹配到具体模板时使用的通用模板
    DEFAULT_VIEW_TEMPLATE = (
        "{view_direction} view of {subject_description}. "
        "Maintain exact same appearance, colors, textures and details. "
        "Clean white background. {extra_requirements}"
    )

    def __init__(self, templates: PromptTemplates) -> None:
        self._templates = templates

    @property
    def templates(self) -> PromptTemplates:
        return self._templates

    def update_templates(self, templates: PromptTemplates) -> None:
        """更新模板（配置变更时调用）"""
        self._templates = templates
        logger.info("Prompt 模板已更新")

    def render_extraction_prompt(
        self,
        custom_prompt: str | None = None,
        **variables: str,
    ) -> str:
        """
        渲染主体提取 Prompt

        Args:
            custom_prompt: 完全自定义 Prompt（优先级最高，直接返回）
            **variables: 模板变量，如 subject_type="卡通角色"

        Returns:
            渲染后的完整 Prompt 字符串
        """
        if custom_prompt:
            logger.debug("使用自定义 extraction prompt")
            return custom_prompt

        defaults = {
            "subject_type": "object",
        }
        defaults.update(variables)

        rendered = self._safe_format(
            self._templates.subject_extraction, **defaults
        )
        logger.debug("渲染 extraction prompt: %s", rendered[:80])
        return rendered

    def render_multiview_prompt(
        self,
        view_name: str,
        custom_prompt: str | None = None,
        **variables: str,
    ) -> str:
        """
        渲染多视角 Prompt

        Args:
            view_name: 视角名称 (front, left_side, back 等)
            custom_prompt: 该视角的完全自定义 Prompt
            **variables: 模板变量

        Returns:
            渲染后的 Prompt
        """
        if custom_prompt:
            logger.debug("使用自定义 %s 视角 prompt", view_name)
            return custom_prompt

        template = self._templates.multiview.get(
            view_name, self.DEFAULT_VIEW_TEMPLATE
        )

        defaults = {
            "view_direction": view_name.replace("_", " "),
            "subject_description": "the subject",
            "extra_requirements": "",
        }
        defaults.update(variables)

        rendered = self._safe_format(template, **defaults)
        logger.debug("渲染 %s 视角 prompt: %s", view_name, rendered[:80])
        return rendered

    @staticmethod
    def _safe_format(template: str, **kwargs: str) -> str:
        """
        安全格式化模板

        未提供的变量保留原始占位符 {var_name}，不会抛出 KeyError。
        """
        fmt = string.Formatter()
        parts: list[str] = []
        for literal_text, field_name, format_spec, conversion in fmt.parse(
            template
        ):
            parts.append(literal_text)
            if field_name is not None:
                value = kwargs.get(field_name)
                if value is not None:
                    parts.append(str(value))
                else:
                    # 保留原始占位符
                    parts.append("{" + field_name + "}")
        return "".join(parts)
