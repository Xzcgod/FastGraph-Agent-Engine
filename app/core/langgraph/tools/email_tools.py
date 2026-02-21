"""邮件发送工具 - 带 Human-in-the-loop（人工审批）中断机制。

Bug 修复记录：
- [Fix-10] 修复 "RuntimeError: This event loop is already running"
- [Fix-SMTP] ✅ 修复 "550 The 'From' header is missing or invalid"
  采用“信封与信纸分离”策略：
  1. 使用 EmailMessage 构建内容，保留 formataddr 格式化的中文发件人名称（给收件人看）。
  2. 使用 server.sendmail() 而非 send_message()。
  3. 显式指定 SMTP 协议层的 MAIL FROM 为纯邮箱地址 (smtp_user)，确保通过 QQ 邮箱校验。
"""

import asyncio
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional, Type

from langchain_core.tools import BaseTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger

# 共享线程池
_thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email_tool")


def _run_async_safely(coro):
    """在同步上下文中安全执行异步协程（与主事件循环隔离）。"""
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    future = _thread_pool.submit(run_in_thread)
    return future.result()


# ========================
# Tool Input Schemas
# ========================
class PrepareEmailInput(BaseModel):
    to_email: str = Field(..., description="收件人邮箱地址")
    subject: str = Field(..., description="邮件主题")
    body: str = Field(..., description="邮件正文内容（支持纯文本）")
    to_name: Optional[str] = Field(default="", description="收件人姓名（可选）")


class SendEmailInput(BaseModel):
    to_email: str = Field(..., description="收件人邮箱地址")
    subject: str = Field(..., description="邮件主题")
    body: str = Field(..., description="邮件正文内容")
    to_name: Optional[str] = Field(default="", description="收件人姓名")


# ========================
# Tools
# ========================
class PrepareEmailTool(BaseTool):
    """准备邮件草稿并请求人工审批（中断执行）。"""

    name: str = "prepare_email"
    description: str = (
        "准备邮件内容并请求用户审批。"
        "在真正发送邮件前，会向用户展示邮件预览，等待确认后才执行发送。"
        "这是高风险操作，必须经过人工审批。"
        "输入：收件人邮箱、主题、正文内容。"
    )
    args_schema: Type[BaseModel] = PrepareEmailInput

    def _run(self, to_email: str, subject: str, body: str, to_name: str = "") -> str:
        """同步调用入口"""
        return _run_async_safely(self._arun(to_email, subject, body, to_name))

    async def _arun(self, to_email: str, subject: str, body: str, to_name: str = "") -> str:
        """
        触发 'interrupt' 中断，暂停 Graph 执行。
        """
        email_preview = {
            "to_email": to_email,
            "to_name": to_name,
            "subject": subject,
            "body": body,
            "from": settings.EMAIL_SMTP_USER
        }

        logger.info("email_approval_requested", **email_preview)

        # 触发中断
        human_review = interrupt(email_preview)

        if str(human_review).lower() in ["approved", "true", "yes"]:
            return (
                f"用户已批准发送邮件。"
                f"请立即调用 send_email 工具，参数："
                f"to_email={to_email}, subject={subject}, body={body}, to_name={to_name}"
            )
        else:
            return f"用户拒绝了发送邮件请求。原因/备注：{human_review}"


class SendEmailTool(BaseTool):
    """真正的邮件发送工具（仅在批准后调用）。"""

    name: str = "send_email"
    description: str = (
        "发送邮件（仅在 prepare_email 工具获得用户批准后调用）。"
        "使用 SMTP 协议真正发出邮件。"
        "输入：收件人邮箱、主题、正文、收件人姓名。"
    )
    args_schema: Type[BaseModel] = SendEmailInput

    def _run(self, to_email: str, subject: str, body: str, to_name: str = "") -> str:
        return _run_async_safely(self._arun(to_email, subject, body, to_name))

    async def _arun(self, to_email: str, subject: str, body: str, to_name: str = "") -> str:
        smtp_host = settings.EMAIL_SMTP_HOST
        smtp_port = settings.EMAIL_SMTP_PORT
        smtp_user = settings.EMAIL_SMTP_USER
        smtp_password = settings.EMAIL_SMTP_PASSWORD

        # 1. 构建邮件对象（信纸）
        # 使用 EmailMessage 自动处理中文编码
        msg = EmailMessage()
        msg.set_content(body)
        msg["Subject"] = subject
        msg["From"] = formataddr((settings.EMAIL_FROM_NAME, smtp_user))
        msg["To"] = formataddr((to_name, to_email)) if to_name else to_email

        def _send_sync():
            try:
                context = ssl.create_default_context() if settings.EMAIL_SMTP_USE_SSL else None

                # 2. 发送邮件（投递信封）
                # 关键修复：使用 server.sendmail() 显式指定 from_addr 为纯邮箱 (smtp_user)
                # 这避免了 send_message() 自动从 msg['From'] 提取 "名称 <邮箱>" 导致 QQ 校验失败
                if settings.EMAIL_SMTP_USE_SSL:
                    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                        server.login(smtp_user, smtp_password)
                        server.sendmail(smtp_user, [to_email], msg.as_string())
                else:
                    with smtplib.SMTP(smtp_host, smtp_port) as server:
                        server.ehlo()
                        server.starttls()
                        server.login(smtp_user, smtp_password)
                        server.sendmail(smtp_user, [to_email], msg.as_string())

                return True
            except Exception as e:
                raise e

        try:
            # 在线程池中执行
            await asyncio.get_event_loop().run_in_executor(None, _send_sync)

            logger.info("email_sent_successfully", to_email=to_email)
            return f"✅ 邮件已成功发送至 {to_email}，主题：「{subject}」"

        except smtplib.SMTPAuthenticationError:
            return "❌ SMTP 认证失败。请检查邮箱授权码是否正确。"
        except Exception as e:
            logger.error("email_smtp_failed", error=str(e), to_email=to_email)
            return f"邮件发送失败（SMTP错误）: {str(e)}"

# 导出工具实例
prepare_email_tool = PrepareEmailTool()
send_email_tool = SendEmailTool()