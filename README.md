🚀 FastAPI + LangGraph 生产级 AI Agent 平台

这是一个企业级、生产就绪的 AI Agent 后端平台。本项目结合了 FastAPI 的高性能异步能力与 LangGraph 的多轮对话图编排能力，为你构建自主智能体（Autonomous Agents）提供了极其稳健的基础设施。

✨ 核心特性 (Features)

🧠 状态化工作流 (Stateful Agent)：基于 LangGraph 构建，内置 PostgreSQL 检查点（Checkpoint）机制，支持多轮、长期记忆压缩的复杂对话。

🔄 高可用大模型路由 (LLM Failover)：深度对接硅基流动 (SiliconFlow) 及 OpenAI 兼容接口，内置指数退避重试，支持模型宕机时的自动无缝切换，保障服务 99.9% 在线。

🧰 动态工具箱 (Dynamic Tools)：根据前端传入的 FeatureFlags 动态挂载能力：

🌐 联网搜索：Tavily API 深度集成（内置 DuckDuckGo 自动降级方案）。

📚 RAG 2.0 知识库：双路混合检索（pgvector 向量 + 关键词）+ 真实的 BGE Reranker 模型重排序。

💾 长期记忆：Agent 自主决策保存和检索用户的长期偏好。

✉️ 带审批的邮件助手：集成 SMTP，包含 HITL (Human-In-The-Loop 人工审批) 中断机制，执行发邮件等高危操作前强制要求用户确认。

🐍 代码沙盒：Python REPL 环境，用于精确的数学计算和数据处理。

👁️ 终极可观测性 (Observability)：

Langfuse：深度的 LLM 调用链路追踪（Trace）、Token 与成本计算。

Prometheus + Grafana：开箱即用的监控大盘，实时追踪 API 延迟、流式输出耗时等指标。

Structlog：带有 session_id 等请求上下文绑定的 JSON 结构化日志。

⚖️ 自动化评估系统 (Evals)：内置 LLM-as-a-judge 脚本，自动从幻觉、有用性、简洁度等 5 个维度对历史对话进行自动化打分。

📚 项目文档

详细的架构说明和测试指南，请参考以下文档：

📖 项目架构与详细说明

🧪 核心功能测试用例

🛠️ 快速开始 (Quick Start)

1. 环境准备

Docker & Docker Compose

Make (可选，推荐用于快捷命令)

2. 配置文件

克隆仓库并设置环境变量：

git clone [https://github.com/yourusername/your-repo-name.git](https://github.com/yourusername/your-repo-name.git)
cd your-repo-name

# 复制环境变量模板
cp .env.example .env.development


打开 .env.development 文件，填入你的各项 API Keys (如 SiliconFlow, Langfuse, 邮箱授权码等)。

3. 一键启动 (Docker)

使用 Docker 启动整个后端技术栈 (包含 API, PostgreSQL, Prometheus, Grafana)：

docker compose --env-file .env.development up -d --build


API 接口文档: http://localhost:8000/docs

Grafana 监控: http://localhost:3000 (账号/密码默认: admin)

4. 本地开发 (不使用 Docker)

如果你想在宿主机纯净运行 Python 代码：

# 使用 uv 安装依赖
pip install uv
uv sync

# 加载环境变量并启动
make dev


🎮 核心功能演示

动态功能开关 (Feature Flags)

调用 /api/v1/chatbot/chat/stream 接口时，前端可以动态控制 Agent 具备的能力：

{
  "messages": [
    {"role": "user", "content": "帮我搜索最新的AI新闻，并总结后发邮件给 boss@example.com"}
  ],
  "features": {
    "web_search": true,
    "email_assistant": true,
    "code_interpreter": false,
    "knowledge_base": false,
    "memory_tools": false
  }
}


人工审批机制 (HITL)

当 Agent 尝试发送邮件时，LangGraph 节点会暂停并返回需要审批的标记信息。前端展示确认框后，调用恢复接口继续执行：

POST /api/v1/chatbot/chat/resume
{
  "session_id": "your-session-uuid",
  "approved": true
}


📜 许可证 (License)

本项目采用 MIT 许可证开源 - 详情请查看 LICENSE 文件。