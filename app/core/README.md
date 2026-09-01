# app/core/ — 核心横切模块

本目录是主后端的**核心基础设施**：配置、日志、监控、限流、中间件，以及 LangGraph 运行时和提示词。它们是整个应用的地基。

## 目录结构

```
core/
├── config.py      # 全局配置（Settings 单例，从环境变量/.env 读取）
├── logging.py     # structlog 结构化日志 + 上下文绑定
├── metrics.py     # Prometheus 指标定义与 /metrics 挂载
├── limiter.py     # slowapi 限流器（基于 IP）
├── middleware.py  # 中间件：日志上下文 + 指标采集
├── langgraph/     # LangGraph Agent 运行时（状态图 + 工具）
└── prompts/       # 系统提示词模板
```

## 各文件职责

| 文件 | 作用 |
|---|---|
| `config.py` | 全局唯一配置源 `settings`，按环境（dev/staging/prod）加载 `.env` |
| `logging.py` | structlog 配置，提供 `logger`、`bind_context`、`clear_context` |
| `metrics.py` | 定义 Counter/Histogram/Gauge，`setup_metrics` 挂载 `/metrics` |
| `limiter.py` | `limiter` 单例，路由用 `@limiter.limit()` 装饰器限流 |
| `middleware.py` | `LoggingContextMiddleware`（JWT→日志上下文）+ `MetricsMiddleware`（请求耗时/计数） |
| `langgraph/` | Agent 执行引擎（见子目录 README） |
| `prompts/` | 系统提示词模板与加载器（见子目录 README） |

## 阅读理解路线

1. **`config.py`** — 先读，它是全局配置源头，几乎所有模块都依赖 `settings`。理解环境加载优先级和各类配置项。
2. **`logging.py`** — 看日志如何初始化，`logger` 与上下文绑定机制。
3. **`middleware.py`** — 看两个中间件如何拦截请求：一个绑定日志上下文，一个采集指标。理解「请求 → LoggingContext → Metrics → 路由」的顺序。
4. **`metrics.py`** + **`limiter.py`** — 看监控与限流的定义方式。
5. **`langgraph/`** — 进入 Agent 核心（单独读子目录 README）。
6. **`prompts/`** — 看系统提示词如何加载与格式化。

> 核心阅读顺序建议：`config.py → logging.py → middleware.py → langgraph/`。前三者支撑了所有请求的横切行为，后者是业务核心。
