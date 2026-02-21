"""Prometheus metrics configuration for the application.
Prometheus 监控指标配置。定义和配置应用监控所需的各项指标。
"""

from prometheus_client import Counter, Histogram, Gauge
# 从 prometheus_client 导入核心指标类型：
# - Counter：只增计数器，用于累计值（如请求总数）。
# - Histogram：直方图，用于记录值的分布（如请求耗时）。
# - Gauge：仪表盘，可增可减，用于当前状态（如活跃连接数）。
from starlette_prometheus import metrics, PrometheusMiddleware
# 从 starlette_prometheus 导入：
# - PrometheusMiddleware：FastAPI/Starlette 中间件，自动收集请求指标。
# - metrics：用于暴露 /metrics 端点的路由处理函数。

# Request metrics
http_requests_total = Counter("http_requests_total", "Total number of HTTP requests", ["method", "endpoint", "status"])
# 定义 HTTP 请求总数计数器，带有 method、endpoint、status 标签。

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds", ["method", "endpoint"]
)
# 定义 HTTP 请求耗时直方图，单位为秒，用于观察请求处理时间的分布。

# Database metrics
db_connections = Gauge("db_connections", "Number of active database connections")
# 定义数据库活跃连接数的仪表盘，可以动态增加或减少。

# Custom business metrics
orders_processed = Counter("orders_processed_total", "Total number of orders processed")
# 业务指标示例：处理订单总数（计数器），可能用于统计。

llm_inference_duration_seconds = Histogram(
    "llm_inference_duration_seconds",
    "Time spent processing LLM inference",
    ["model"], # 标签：使用的模型名称
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0] # 自定义分桶，更精细地记录延迟分布
)
# LLM 推理耗时直方图，按模型标签区分，自定义分桶以适应 LLM 延迟范围。

llm_stream_duration_seconds = Histogram(
    "llm_stream_duration_seconds",
    "Time spent processing LLM stream inference",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]# 流式推理耗时通常更长，分桶范围更大
)
# LLM 流式推理耗时直方图，同样按模型标签区分。

def setup_metrics(app):
    """Set up Prometheus metrics middleware and endpoints.

    Args:
        app: FastAPI application instance
    """
    # 向 FastAPI 应用添加 Prometheus 中间件，该中间件会自动收集请求信息（如耗时、状态码）。
    app.add_middleware(PrometheusMiddleware)

    # 添加 /metrics 路由，当 Prometheus 服务抓取指标时会调用该路由，返回所有已注册指标。
    app.add_route("/metrics", metrics)
# 这个函数通常在应用启动时调用（如 main.py 中），完成监控的挂载。