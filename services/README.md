# services/ — 独立服务

本目录存放与主后端 `app/` 解耦的**独立服务**。当前只有 `knowledge_service`（知识库微服务），它是三层架构中的第三层。

## 目录结构

```
services/
├── __init__.py          # 包标记
└── knowledge_service/   # 独立知识库微服务（见子目录 README）
```

## 与 app/ 的关系

- `app/`（主后端 control-plane）通过 `app/services/knowledge_client.py` 访问这里的 knowledge-service。
- knowledge-service 只暴露内部 API（`/internal/v1/kb/*`），由主后端代理，**浏览器不直接访问**。
- 服务间认证用 `X-KB-Service-Token`，并透传操作人（`X-Actor-User-Id`/`X-Actor-Email`）。

## 阅读理解路线

1. **`knowledge_service/`** — 直接进入子目录，按子目录 README 的顺序读。
