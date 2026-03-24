"""
Easy AIGC — FastAPI 应用入口

启动命令: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.providers.evolink import EvolinkProvider
from app.providers.registry import ProviderRegistry
from app.providers.siliconflow import SiliconFlowProvider
from app.routers import config_router, generation, model_router
from app.services.model_generator import ModelGenerator
from app.services.multiview_generator import MultiViewGenerator
from app.services.prompt_engine import PromptEngine
from app.services.storyboard_generator import StoryboardGenerator
from app.services.subject_extractor import SubjectExtractor
from app.utils.storage import StorageManager

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 启动时初始化所有组件"""
    logger.info("=== Easy AIGC 启动中 ===")

    # 1. 加载配置
    settings = get_settings()
    logger.info("配置已加载, 默认 Provider: %s", settings.default_provider)

    # 2. 初始化 Provider Registry
    registry = ProviderRegistry()

    # 注册 SiliconFlow Provider
    sf_config = settings.providers.get("siliconflow")
    if sf_config and sf_config.enabled:
        registry.register(SiliconFlowProvider(sf_config))

    # 注册 Evolink Provider
    ev_config = settings.providers.get("evolink")
    if ev_config and ev_config.enabled:
        registry.register(EvolinkProvider(ev_config))

    logger.info(
        "已注册 Provider: %s",
        registry.list_names(),
    )

    # 3. 初始化 Prompt Engine
    prompt_engine = PromptEngine(settings.prompts)

    # 4. 初始化 Storage Manager
    storage = StorageManager(settings.output_base_path)

    # 5. 初始化业务服务
    extractor = SubjectExtractor(registry, storage, prompt_engine)
    multiview = MultiViewGenerator(registry, storage, prompt_engine)

    # 6. 初始化模特生成服务
    model_gen = ModelGenerator(
        registry=registry,
        storage=storage,
        prompt_engine=prompt_engine,
        multiview=multiview,
        models_base_path=settings.models_base_path,
    )

    # 7. 初始化分镜脚本生成服务
    storyboard_gen = StoryboardGenerator(
        registry=registry,
        storage=storage,
        prompt_engine=prompt_engine,
    )

    # 8. 注入到路由
    generation.set_services(extractor, multiview, storyboard_gen)
    config_router.set_registry(registry)
    model_router.set_model_generator(model_gen)

    logger.info("=== Easy AIGC 启动完成 ===")

    yield

    logger.info("=== Easy AIGC 已关闭 ===")


# ---------- 创建应用 ----------

app = FastAPI(
    title="Easy AIGC",
    description=(
        "基于多 Provider 抽象架构的图片主体提取与多视角生成服务。\n\n"
        "支持 SiliconFlow、Evolink 等多个 AI API 提供商，\n"
        "Prompt 模板引擎支持动态注入与持久化配置。"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(generation.router)
app.include_router(config_router.router)
app.include_router(model_router.router)

# 前端静态文件
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="frontend")

# 生成结果图片目录
_output_dir = Path(__file__).resolve().parent.parent / "output"
_output_dir.mkdir(exist_ok=True)
app.mount("/output", StaticFiles(directory=str(_output_dir)), name="output")

# 模特图片目录
_models_dir = Path(__file__).resolve().parent.parent / "output" / "models"
_models_dir.mkdir(parents=True, exist_ok=True)
app.mount("/models", StaticFiles(directory=str(_models_dir)), name="models")


# ---------- 根路由 ----------

@app.get("/", tags=["Health"])
async def root():
    """返回前端页面"""
    index_path = _frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(
            str(index_path),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return {"service": "Easy AIGC", "version": "0.1.0", "docs": "/docs"}


@app.get("/health", tags=["Health"])
async def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "default_provider": settings.default_provider,
        "providers": list(settings.providers.keys()),
    }
