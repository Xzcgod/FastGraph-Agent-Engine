# 🚀 FastGraph Agent Engine

一个基于 **FastAPI + LangGraph** 的生产级 AI Agent 平台，采用「前端控制台 / 主后端 control-plane / 知识库微服务」三层架构，支持多模型路由、动态工具、知识库检索、人工审批（HITL）和全链路可观测性。

## 🏗️ 架构设计

### 三层架构

```
前端控制台 (frontend/)                    端口 5174
  ├─ /api/v1/auth/*              认证：注册/登录/当前用户（区分管理员与普通用户）
  ├─ /api/v1/admin/platform/*    平台管理：Agent 配置 + 知识库/文档/入库任务代理
  └─ /api/v1/agents/*            普通用户：调用已发布 Agent（流式）
        │
        ▼
主后端 control-plane (app/)               端口 8000
  ├─ api/                REST 路由层（薄壳，只做参数校验与转发）
  ├─ services/           业务服务层：LLM 路由 / Agent 配置 / knowledge 代理 / 数据库
  ├─ core/langgraph/     Agent 执行引擎：状态图（agent ⇄ tools）+ 动态工具
  ├─ models/ + schemas/  数据库表（SQLModel）+ API 契约（Pydantic）
  └─ utils/              通用工具：JWT / 消息处理 / 数据净化
        │  X-KB-Service-Token（服务间认证）
        ▼
知识库微服务 (services/knowledge_service/)  端口 8010
  ├─ 文档上传 → 解析 → 切片 → embedding → 入库任务（状态机）
  └─ 可插拔检索算法（vector/weighted/hybrid/keyword/fulltext/keyword_rank，向量类支持 rerank 变体）
```

### 核心数据流

1. **平台管理员**在控制台创建知识库、上传文档（解析 + 切片 + embedding + 入库任务记录），配置 Agent（模型、角色、工具开关、知识库绑定）并发布。
2. **普通用户**选择已发布 Agent 发起对话，主后端读取 Agent 配置。
3. Agent 启用知识库时，LLM 通过 `knowledge_base_search` **工具按需检索**——检索参数（topK/scoreThreshold）经 LangGraph 的 `InjectedState` 从图状态注入对 LLM 不可见；`kb_id` 可由 LLM 从绑定知识库中自选；不预改写用户消息。
4. LangGraph 状态图（agent ⇄ tools 循环）驱动多轮对话，PostgreSQL Checkpoint 持久化状态，支持 HITL 中断（如邮件审批）。

## ✨ 核心特性

- 🧠 **状态化工作流**：基于 LangGraph，PostgreSQL Checkpoint 持久化，支持多轮对话与长期记忆压缩。
- 🔄 **高可用模型路由**：对接 DeepSeek 官方及 OpenAI 兼容接口，内置指数退避重试与模型故障自动切换。
- 🧰 **动态工具箱**：按 Feature Flag 动态挂载工具——联网搜索（AnySearch/DuckDuckGo）、知识库检索、长期记忆、邮件助手、代码沙盒。
- 📚 **独立知识库服务**：文档上传、切片、多算法可插拔检索由 `services/knowledge_service` 负责，主后端只做权限校验与代理。检索算法支持 vector/weighted/hybrid/keyword/fulltext/keyword_rank，向量类可配 rerank 变体；每个知识库可独立配置检索算法与联网兜底。
- 💾 **长期记忆**：Agent 自主保存/检索用户偏好。
- ✉️ **带审批的邮件助手**：HITL 中断，发邮件前强制人工确认。
- 👁️ **可观测性**：Langfuse 链路追踪 + Prometheus/Grafana 监控 + structlog 结构化日志。

## 🛠️ 快速开始

```bash
git clone https://github.com/Xzcgod/FastGraph-Agent-Engine.git
cd FastGraph-Agent-Engine

# 复制环境变量模板
cp .env.example .env.development
```

按需填入 DeepSeek API Key、Langfuse Key、邮箱授权码等，然后本地混合启动（Docker 跑基础设施，三层代码跑宿主机）：

```powershell
scripts\start-docker.cmd   # PostgreSQL/pgvector、Ollama、Prometheus、Grafana
scripts\start-local.cmd    # knowledge-service、主后端、前端
```

访问地址：前端控制台 http://127.0.0.1:5174 · API 文档 http://localhost:8000/docs · Grafana http://localhost:3000

## 🌐 线上部署

生产环境已部署于阿里云轻量服务器，实际访问地址：

- **控制台**：http://47.122.117.96/
- **部署说明**：`docs/部署-阿里云轻量服务器.md`

> 生产运行在 `slim-deploy` 分支（瘦身版：仅容器化数据库、embedding/LLM 走外部 API、nginx 反代，已移除监控三件套与评估模块）；本地开发主分支为 `main`。

## 📚 项目文档

- 📖 各目录结构说明与阅读路线：`app/README.md`、`services/README.md` 及各自子目录
- 📌 三层架构与本地混合开发：`docs/三层架构本地开发.md`

## 🙏 致谢

本项目基于 [tring-yu/FastGraph-Agent-Engine](https://github.com/tring-yu/FastGraph-Agent-Engine) 二次开发，感谢原项目的贡献。

## 📜 许可证

本项目采用 MIT 许可证开源 - 详情请查看 LICENSE 文件。
