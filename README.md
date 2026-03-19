# Easy AIGC

基于多 Provider 抽象架构的图片主体提取与多视角生成服务。

## 功能

- **主体提取**: 从输入图片中提取主体，去除背景
- **多视角生成**: 基于主体生成正面、侧面、背面等多个视角的一致性图片
- **多 Provider 支持**: SiliconFlow、Evolink 等，可插拔扩展
- **Prompt 动态注入**: 模板化配置 + 请求级变量注入/完全覆盖
- **配置持久化**: YAML 文件持久化，支持 API 在线修改

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key（选择其一）
export SILICONFLOW_API_KEY=sk-your-key
# 或编辑 config/settings.yaml

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 Swagger UI: http://localhost:8000/docs

## API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/generation/extract-subject` | 主体提取 |
| `POST` | `/api/v1/generation/multi-view` | 多视角生成 |
| `POST` | `/api/v1/generation/pipeline` | 完整流水线 |
| `GET`  | `/api/v1/config` | 获取配置 |
| `PUT`  | `/api/v1/config` | 更新配置 |
| `PUT`  | `/api/v1/config/prompts` | 更新 Prompt 模板 |
| `GET`  | `/api/v1/config/providers` | 列出 Provider |

## 扩展新 Provider

1. 创建 `app/providers/new_provider.py`
2. 继承 `ImageProvider`，实现 3 个方法
3. 在 `app/main.py` 的 `lifespan` 中注册

## 项目结构

```
app/
├── main.py              # 应用入口
├── config.py            # 配置管理
├── models/schemas.py    # 数据模型
├── providers/           # Provider 抽象层
│   ├── base.py          # ABC 基类
│   ├── registry.py      # 注册中心
│   ├── siliconflow.py   # SiliconFlow
│   └── evolink.py       # Evolink
├── services/            # 业务服务
│   ├── prompt_engine.py # Prompt 模板引擎
│   ├── subject_extractor.py
│   └── multiview_generator.py
├── routers/             # API 路由
│   ├── generation.py
│   └── config_router.py
└── utils/               # 工具
    ├── image_utils.py
    └── storage.py
```
