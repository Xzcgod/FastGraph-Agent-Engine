"""
Prometheus 监控指标配置模块。

本模块定义了应用监控所需的各项 Prometheus 指标，并提供了挂载函数。

指标类型说明：
- Counter（计数器）：只增不减，用于累计值。如请求总数、错误总数。
- Histogram（直方图）：记录值的分布。如请求耗时分布、响应大小分布。
- Gauge（仪表盘）：可增可减，反映当前瞬时状态。如活跃连接数、内存使用量。

指标分类：
1. HTTP 请求指标：请求总数、请求耗时。
2. 数据库指标：活跃连接数。
3. 业务指标：订单处理数（示例）。
4. LLM 指标：推理耗时、流式推理耗时（按模型分桶）。
"""

from prometheus_client import Counter, Histogram, Gauge
# Counter: 只增计数器，适用于请求总数、错误总数等累计指标。
# Histogram: 直方图，适用于请求耗时、响应大小等需要观察分布的指标。
# Gauge: 仪表盘，适用于活跃连接数、队列长度等可增可减的瞬时指标。
from starlette_prometheus import metrics
# metrics 是 starlette_prometheus 提供的路由处理函数，
# 用于暴露 /metrics 端点，返回所有已注册指标的当前值。

# ============================================================================
# HTTP 请求指标
# ============================================================================

# 请求总数计数器
# labels=["method", "endpoint", "status"] 允许按 HTTP 方法、路径、状态码分组统计
# 例如：统计 GET /api/v1/chat 的 200 请求数
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"]
)

# 请求耗时直方图
# 单位为秒，labels=["method", "endpoint"] 允许按方法和路径分组
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)

# ============================================================================
# 数据库指标
# ============================================================================

# 数据库活跃连接数仪表盘
# 可在连接池获取/归还连接时调整此值，反映当前数据库连接使用情况
db_connections = Gauge(
    "db_connections",
    "Number of active database connections"
)

# ============================================================================
# 业务指标（示例）
# ============================================================================

# 处理订单总数计数器 - 业务指标示例，可根据实际需求替换或删除
orders_processed = Counter(
    "orders_processed_total",
    "Total number of orders processed"
)

# ============================================================================
# LLM 指标
# ============================================================================

# LLM 普通推理耗时直方图
# labels=["model"] 允许按模型名称分组
# 自定义分桶：针对 LLM 推理延迟特点（通常在 100ms ~ 5s 范围）设置更精细的分桶
llm_inference_duration_seconds = Histogram(
    "llm_inference_duration_seconds",
    "Time spent processing LLM inference",
    ["model"],
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0]
)

# LLM 流式推理耗时直方图
# 流式推理由于逐 Token 返回，总耗时通常更长
# 分桶范围比普通推理更大（0.1s ~ 10s）
llm_stream_duration_seconds = Histogram(
    "llm_stream_duration_seconds",
    "Time spent processing LLM stream inference",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)


# ============================================================================
# 指标挂载函数
# ============================================================================

def setup_metrics(app):
    """
    将 /metrics 端点挂载到 FastAPI 应用。

    该端点返回 Prometheus 格式的指标数据，可被 Prometheus Server 定期抓取。
    请求指标（http_requests_total、http_request_duration_seconds）由
    app.core.middleware.MetricsMiddleware 自动采集。

    使用方式：
        # 在 main.py 中
        from app.core.metrics import setup_metrics
        setup_metrics(app)
        # 之后访问 http://localhost:8000/metrics 即可获取指标数据

    Args:
        app: FastAPI 应用实例。
    """
    app.add_route("/metrics", metrics)
