"""文件名：llm.py
作用：管理与 AI 模型的连接，包含自动重试和备用模型切换功能."""

from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
# 导入 OpenAI 的各种错误类型（超时、限流、API错误）
from openai import (
    APIError,
    APITimeoutError,
    OpenAIError,
    RateLimitError,
)
# tenacity 是一个专门用来“重试”的库
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger


class LLMRegistry:
    """【通讯录】
    这个类就像一个菜单，列出了我们所有能用的 AI 模型。
    """

    # 类级别的变量，存储所有可用的 LLM 模型
    # 每个元素是一个字典，包含模型名称和对应的 ChatOpenAI 实例
    LLMS: List[Dict[str, Any]] = [
        {
            "name": "deepseek-ai/DeepSeek-V3.2",
            "llm": ChatOpenAI(
                model="deepseek-ai/DeepSeek-V3.2",
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,#连接硅基流动的关键
                temperature=settings.DEFAULT_LLM_TEMPERATURE,#控制模型温度的
                max_tokens=settings.MAX_TOKENS,
               # reasoning={"effort": "low"},暂时移除防止deepseek不报错
            ),
        },
        {
            "name": "deepseek-ai/DeepSeek-V3",
            "llm": ChatOpenAI(
                model="deepseek-ai/DeepSeek-V3",
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,  # 连接硅基流动的关键
                temperature=settings.DEFAULT_LLM_TEMPERATURE,#控制模型温度
                max_tokens=settings.MAX_TOKENS,
              #  reasoning={"effort": "medium"},
            ),
        },
        {
            "name": "Qwen/Qwen3-VL-32B-Instruct",
            "llm": ChatOpenAI(
                model="Qwen/Qwen3-VL-32B-Instruct",
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,  # 连接硅基流动的关键
                temperature=settings.DEFAULT_LLM_TEMPERATURE,  # 控制模型温度
                max_tokens=settings.MAX_TOKENS,
               # reasoning={"effort": "minimal"},
            ),
        },
        {
            "name": "zai-org/GLM-4.5V",
            "llm": ChatOpenAI(
                model="zai-org/GLM-4.5V",
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,  # 连接硅基流动的关键
                max_tokens=settings.MAX_TOKENS,
                # top_p=0.95 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.8,
                # presence_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
                # frequency_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
            ),
        },
        {
            "name": "Qwen/Qwen3-VL-8B-Instruct",
            "llm": ChatOpenAI(
                model="Qwen/Qwen3-VL-8B-Instruct",
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                base_url=settings.OPENAI_BASE_URL,  # 连接硅基流动的关键
                #top_p=0.9 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.8,
            ),
        },
    ]

    @classmethod
    def get(cls, model_name: str, **kwargs) -> BaseChatModel:
        """根据模型名称返回对应的 LLM 实例。
        如果提供了额外的 kwargs，则会用这些参数创建一个新的 ChatOpenAI 实例（覆盖默认参数）。
        """
        # 1. 在列表里找名字匹配的模型
        model_entry = None
        for entry in cls.LLMS:
            if entry["name"] == model_name:
                model_entry = entry
                break
        # 2. 如果没找到，报错并列出可用模型
        if not model_entry:
            available_models = [entry["name"] for entry in cls.LLMS]
            raise ValueError(
                f"model '{model_name}' not found in registry. available models: {', '.join(available_models)}"
            )

        # 3. 如果传入了自定义参数（如 temperature、max_tokens 等），则创建一个新的实例
        if kwargs:
            logger.debug("creating_llm_with_custom_args", model_name=model_name, custom_args=list(kwargs.keys()))
            return ChatOpenAI(model=model_name, api_key=settings.OPENAI_API_KEY, **kwargs)

        # 4. 否则直接返回预先准备好的那个
        logger.debug("using_default_llm_instance", model_name=model_name)
        return model_entry["llm"]

    @classmethod
    def get_all_names(cls) -> List[str]:
        """作用：返回所有可用模型的名称列表。
        """
        # 列表推导式：遍历 LLMS 列表，只取出每个字典里的 "name" 字段
        return [entry["name"] for entry in cls.LLMS]

    @classmethod
    def get_model_at_index(cls, index: int) -> Dict[str, Any]:
        """根据索引获取模型条目（字典，包含 name 和 llm）。
        如果索引越界，则返回第一个（安全机制，防止崩溃）。
        """
        # 检查编号有没有越界（比如一共3个模型，你不能要第10个）
        if 0 <= index < len(cls.LLMS):
            return cls.LLMS[index]
        # 如果越界了（比如转了一圈回到原点了），就默认返回第一个
        # 这是一种安全机制，防止程序崩溃
        return cls.LLMS[0]  # Wrap around to first model


class LLMService:
    """这是真正干活的类。它负责：
    - 调用 AI 模型（打电话）
    - 处理临时故障（如限流、超时）并自动重试
    - 如果一个模型彻底失败，自动切换到下一个可用模型（备胎切换）
    - 支持临时指定模型和参数
    """

    def __init__(self):
        """初始化默认使用哪个模型."""
        self._llm: Optional[BaseChatModel] = None#当前使用的 LLM 实例
        self._current_model_index: int = 0# 当前模型在注册表中的索引（第几个备胎）

        # 1. 拿到所有模型的名字列表
        all_names = LLMRegistry.get_all_names()
        try:
            # 2. 尝试定位默认模型
            # 假设 settings.DEFAULT_LLM_MODEL 是 "gpt-4o"
            # .index() 方法会查找 "gpt-4o" 在列表里的位置（比如是第 1 号）
            self._current_model_index = all_names.index(settings.DEFAULT_LLM_MODEL)
            # 3. 实例化默认模型
            self._llm = LLMRegistry.get(settings.DEFAULT_LLM_MODEL)
            # 记录成功日志
            logger.info(
                "llm_service_initialized",
                default_model=settings.DEFAULT_LLM_MODEL,
                model_index=self._current_model_index,
                total_models=len(all_names),
                environment=settings.ENVIRONMENT.value,
            )
        except (ValueError, Exception) as e:
            # === 异常处理 / 保底逻辑 ===
            # 如果 .index() 找不到名字，会抛出 ValueError。
            # 这时候说明配置文件里写的默认模型名字是错的，或者不存在。 强制使用列表中的第一个模型作为保底。
            # 1. 强制重置为 0 号（列表第一个）
            self._current_model_index = 0
            # 2. 强制使用列表里的第一个模型作为实体
            self._llm = LLMRegistry.LLMS[0]["llm"]
            # 记录警告日志，告诉管理员：“你配置的模型找不到，我自作主张用了第一个”
            logger.warning(
                "default_model_not_found_using_first",
                requested=settings.DEFAULT_LLM_MODEL,
                using=all_names[0] if all_names else "none",
                error=str(e),
            )

    def _get_next_model_index(self) -> int:
        """【备胎算法】
        这是一个“循环计数器”。
        假设总共有 3 个模型 (索引 0, 1, 2)。
        """
        total_models = len(LLMRegistry.LLMS)
        # 核心数学逻辑：取模运算 (%)
        # 假设当前是 0: (0 + 1) % 3 = 1  -> 下一个是 1
        # 假设当前是 1: (1 + 1) % 3 = 2  -> 下一个是 2
        # 假设当前是 2: (2 + 1) % 3 = 0  -> 下一个是 0 (回到开头！)
        next_index = (self._current_model_index + 1) % total_models
        return next_index

    def _switch_to_next_model(self) -> bool:
        """ 【执行切换】
        真正执行“换人”的操作。
        """
        try:
            # 1. 算一下下一个是谁
            next_index = self._get_next_model_index()
            # 2. 把下一个人的资料拿出来
            next_model_entry = LLMRegistry.get_model_at_index(next_index)
            # 记录警告：正在发生切换
            logger.warning(
                "switching_to_next_model",
                from_index=self._current_model_index,
                to_index=next_index,
                to_model=next_model_entry["name"],
            )
            # 3.更新当前索引和 LLM 实例
            self._current_model_index = next_index
            # 4. 替换掉手里的 LLM 实例
            self._llm = next_model_entry["llm"]

            logger.info("model_switched", new_model=next_model_entry["name"], new_index=next_index)
            return True
        except Exception as e:
            logger.error("model_switch_failed", error=str(e))
            return False

    # 🛡️ tenacity 装饰器：为 _call_llm_with_retry 方法添加自动重试能力
    # 它的作用是：把下面这个函数包裹起来，给它穿上一层“复活甲”
    @retry(
        stop=stop_after_attempt(settings.MAX_LLM_CALL_RETRIES),# 最多重试 N 次（由配置决定）
        wait=wait_exponential(multiplier=1, min=2, max=10), # 指数退避等待：第一次失败等 2s，第二次 4s，第三次 8s...
        # 策略 3：只救“可救”之错
        # 并不是所有错误都重试。
        # 比如“密码错误”重试一万次也没用。
        # 这里指定：只有 限流、超时、服务器内部错误 这三种情况才重试。
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIError)),
        # 策略 4：每次睡觉（等待重试）前，记录一条日志
        # 让我们知道：“哦，刚才失败了，正在准备第 N 次尝试...”
        before_sleep=before_sleep_log(logger, "WARNING"),
        # 策略 5：如果最后还是失败了，把最后一次遇到的那个错误抛出来
        # 不要吞掉错误，让上层逻辑知道具体是哪里挂了。
        reraise=True,# 如果最终失败，抛出最后一次异常
    )
    async def _call_llm_with_retry(self, messages: List[BaseMessage]) -> BaseMessage:
        """核心调用方法：使用当前模型异步调用 LLM，并带有重试机制。
        如果遇到可重试错误，会由装饰器自动重试；遇到不可重试错误则直接抛出。
        """
        if not self._llm:
            raise RuntimeError("llm not initialized")

        try:
            # ainvoke 是 LangChain 的异步调用方法
            response = await self._llm.ainvoke(messages)
            # 3. 如果成功了，记个日记，然后把结果返回去
            logger.debug("llm_call_successful", message_count=len(messages))
            return response
        # === 异常捕获区 ===
        # 注意：这里的 except 主要是为了记录日志，
        # 记录完之后必须 raise，这样外面的 @retry 装饰器才能感知到错误，从而触发重试。
        except (RateLimitError, APITimeoutError, APIError) as e:
            # 可重试的错误：记录警告后重新抛出，让装饰器处理重试
            logger.warning(
                "llm_call_failed_retrying",
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )
            raise# 【关键！】把错误扔出去，让 @retry 接住并安排重试
        except OpenAIError as e:
            # 其他 OpenAI 错误（如认证错误、无效请求等），不可重试，直接记录错误并抛出
            # @retry 装饰器没配置这几种错误，所以一旦 raise 出去，程序就真的报错停止了。
            logger.error(
                "llm_call_failed",
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def call(
        self,
        messages: List[BaseMessage],
        model_name: Optional[str] = None,
        **model_kwargs,
    ) -> BaseMessage:
        """    【对外接口】调用 LLM，支持指定模型、自定义参数，并内置故障切换逻辑。
        如果指定了 model_name，则临时使用该模型（覆盖当前默认）。
        调用流程：
          - 如果指定模型，先获取该模型实例并更新索引。
          - 然后循环尝试当前模型（最多尝试所有模型）：
              * 调用 _call_llm_with_retry（内部有重试）
              * 如果成功则返回结果
              * 如果失败（最终失败），则切换到下一个模型继续尝试
          - 如果所有模型都失败，抛出 RuntimeError。
        """
        # If user specifies a model, get it from registry
        if model_name:
            try:
                self._llm = LLMRegistry.get(model_name, **model_kwargs)
                # Update index to match the requested model
                all_names = LLMRegistry.get_all_names()
                try:
                    self._current_model_index = all_names.index(model_name)
                except ValueError:
                    pass  # 如果模型名称不在列表中（可能因为自定义参数新建的），保持当前索引不变
                logger.info("using_requested_model", model_name=model_name, has_custom_kwargs=bool(model_kwargs))
            except ValueError as e:
                logger.error("requested_model_not_found", model_name=model_name, error=str(e))
                raise

        # Track which models we've tried to prevent infinite loops
        total_models = len(LLMRegistry.LLMS)# 总共有几个备胎
        models_tried = 0
        starting_index = self._current_model_index# 记住是从谁开始试的
        last_error = None
        # 只要试过的数量还没超过总数，就一直循环
        while models_tried < total_models:
            try:
                response = await self._call_llm_with_retry(messages)
                return response# 通了！直接返回，结束函数。
            except OpenAIError as e:
                last_error = e
                # 2. 如果当前这个模型彻底打不通 (重试几次都失败)
                models_tried += 1
                # 记录错误
                current_model_name = LLMRegistry.LLMS[self._current_model_index]["name"]
                logger.error(
                    "llm_call_failed_after_retries",
                    model=current_model_name,
                    models_tried=models_tried,
                    total_models=total_models,
                    error=str(e),
                )

                # 3. 关键点：如果试了一圈全挂了，就别试了，直接跳出循环
                if models_tried >= total_models:
                    logger.error(
                        "all_models_failed",
                        models_tried=models_tried,
                        starting_model=LLMRegistry.LLMS[starting_index]["name"],
                    )
                    break

                # # 4. 关键点：切换到下一个备胎，进入下一次 while 循环
                if not self._switch_to_next_model():
                    logger.error("failed_to_switch_to_next_model")
                    break

                # Continue loop to try next model

        # 如果 while 循环结束了还没 return，说明所有模型全军覆没
        raise RuntimeError(
            f"failed to get response from llm after trying {models_tried} models. last error: {str(last_error)}"
        )

    def get_llm(self) -> Optional[BaseChatModel]:
        """【获取当前模型】
        返回当前使用的 LLM 实例，供外部使用（例如计算 token 数）。
        """
        return self._llm

    def bind_tools(self, tools: List) -> "LLMService":
        """ 给当前 LLM 绑定工具（如联网搜索、计算器等），
        这是 LangChain 的功能，绑定后模型可以调用这些工具。
        返回 self 以支持链式调用。。
        """
        if self._llm:
            # 这一步是 LangChain 的标准操作：把工具绑定到模型上
            # 绑定后，模型就知道自己手头有哪些工具可以用
            self._llm = self._llm.bind_tools(tools)
            logger.debug("tools_bound_to_llm", tool_count=len(tools))
            # 返回自己 (self) 是为了支持“链式调用”
            # 也就是可以写成：llm_service.bind_tools(tools).call(messages) 这样连着写
        return self


# 创建全局单例
llm_service = LLMService()