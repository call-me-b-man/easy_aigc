"""
文件存储管理 — 负责任务目录创建、图片下载保存、元数据记录
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.providers.base import ProviderResult
from app.utils.image_utils import base64_to_bytes

logger = logging.getLogger(__name__)


class StorageManager:
    """
    文件存储管理器

    目录结构:
        output_base/
        └── YYYY-MM-DD/
            └── {task_id}/
                ├── original.png
                ├── subject.png
                ├── view_front.png
                ├── metadata.json
                ...
    """

    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path)

    @property
    def base_path(self) -> Path:
        return self._base_path

    def update_base_path(self, new_path: str | Path) -> None:
        """更新存储根路径"""
        self._base_path = Path(new_path)

    def get_task_dir(self, task_id: str) -> Path:
        """
        创建并返回任务级别的输出目录

        格式: base_path/YYYY-MM-DD/task_id/
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        task_dir = self._base_path / date_str / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    async def save_from_result(
        self,
        result: ProviderResult,
        task_dir: Path,
        filename: str,
    ) -> Path | None:
        """
        从 ProviderResult 保存图片到本地

        优先使用 image_url (下载), 其次 image_base64 (解码)

        Args:
            result: Provider 返回的生成结果
            task_dir: 任务输出目录
            filename: 文件名 (不含扩展名)

        Returns:
            保存后的文件路径, 失败返回 None
        """
        if result.image_url:
            return await self.save_from_url(result.image_url, task_dir, filename)
        elif result.image_base64:
            return self.save_from_base64(result.image_base64, task_dir, filename)
        else:
            logger.warning("ProviderResult 中无图片数据")
            return None

    async def save_from_url(
        self,
        url: str,
        task_dir: Path,
        filename: str,
    ) -> Path:
        """
        从 URL 下载图片并保存

        注意: SiliconFlow URL 有效期仅 1 小时，需立即下载
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                # 从 Content-Type 推断扩展名
                content_type = response.headers.get("content-type", "image/png")
                ext_map = {
                    "image/png": ".png",
                    "image/jpeg": ".jpg",
                    "image/webp": ".webp",
                    "image/gif": ".gif",
                }
                ext = ".png"
                for ct, extension in ext_map.items():
                    if ct in content_type:
                        ext = extension
                        break

                save_path = task_dir / f"{filename}{ext}"
                save_path.write_bytes(response.content)
                logger.info("图片已保存: %s (%d bytes)", save_path, len(response.content))
                return save_path

        except Exception as e:
            logger.error("下载图片失败 (%s): %s", url[:60], str(e))
            raise

    @staticmethod
    def save_from_base64(
        b64_data: str,
        task_dir: Path,
        filename: str,
    ) -> Path:
        """从 base64 数据保存图片"""
        img_bytes, ext = base64_to_bytes(b64_data)
        save_path = task_dir / f"{filename}{ext}"
        save_path.write_bytes(img_bytes)
        logger.info("图片已保存(base64): %s (%d bytes)", save_path, len(img_bytes))
        return save_path

    async def save_uploaded_image(
        self,
        content: bytes,
        task_dir: Path,
        filename: str = "original",
        ext: str = ".png",
    ) -> Path:
        """保存上传的图片文件"""
        save_path = task_dir / f"{filename}{ext}"
        save_path.write_bytes(content)
        logger.info("上传图片已保存: %s (%d bytes)", save_path, len(content))
        return save_path

    @staticmethod
    def save_metadata(
        task_dir: Path,
        metadata: dict[str, Any],
    ) -> Path:
        """保存任务元数据到 JSON 文件"""
        meta_path = task_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)
        return meta_path

    @staticmethod
    def load_metadata(task_dir: Path) -> dict[str, Any] | None:
        """加载任务元数据"""
        meta_path = task_dir / "metadata.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
