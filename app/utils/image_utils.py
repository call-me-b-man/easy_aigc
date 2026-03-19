"""
图片处理工具 — base64 编解码、格式检测等
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path


def image_to_base64(image_path: str | Path) -> str:
    """
    读取本地图片文件并转换为 base64 字符串

    Returns:
        data:image/<mime>;base64,<data> 格式的字符串
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图片文件不存在: {path}")

    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    raw_data = path.read_bytes()
    b64_data = base64.b64encode(raw_data).decode("utf-8")
    return f"data:{mime_type};base64,{b64_data}"


def base64_to_bytes(b64_string: str) -> tuple[bytes, str]:
    """
    解码 base64 图片字符串

    Args:
        b64_string: 可以是 "data:image/png;base64,..." 或纯 base64

    Returns:
        (图片字节数据, 文件扩展名 如 ".png")
    """
    ext = ".png"  # 默认扩展名

    if b64_string.startswith("data:"):
        # 解析 data URI
        header, data = b64_string.split(",", 1)
        mime = header.split(";")[0].split(":")[1]
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
        }
        ext = ext_map.get(mime, ".png")
    else:
        data = b64_string

    return base64.b64decode(data), ext


def is_url(value: str) -> bool:
    """判断字符串是否是 URL"""
    return value.startswith("http://") or value.startswith("https://")


def is_base64(value: str) -> bool:
    """判断字符串是否是 base64 编码的图片"""
    return value.startswith("data:image/") or (
        len(value) > 100 and not is_url(value)
    )


def get_image_extension(filename: str) -> str:
    """从文件名获取图片扩展名"""
    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
        return ext
    return ".png"
