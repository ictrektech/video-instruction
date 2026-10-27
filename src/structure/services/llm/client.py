from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import openai
from openai import Omit
from openai.types.chat import ChatCompletionMessageParam

from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.utils.video_source import redact_url
from structure.services.llm.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


async def _no_credentials() -> str:
    """空密钥占位：让 SDK 通过构造期凭据校验，实际请求再由 Omit 省略 Authorization 头。"""
    return ""


_IMAGE_EXT_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# 推理型模型的 reasoning_content 计入 max_tokens，预算过小会返回空 content
_MAX_TOKENS = 1024


def _upstream_fields(exc: openai.APIStatusError) -> dict[str, str]:
    """从 OpenAI 兼容网关的错误体里取 code/msg/request_id（V-Scheduler 是标准 JSON）。

    网关不再回显被请求的 model id，所以调用方需要这些字段来定位问题。
    """
    body: dict = {}
    try:
        raw = exc.response.text if exc.response is not None else ""
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            body = parsed
    except (ValueError, TypeError):  # 错误体不是 JSON：退回 SDK 字段
        pass
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    return {
        "code": str(body.get("code") or err.get("code") or ""),
        "msg": str(body.get("msg") or err.get("message") or ""),
        "request_id": str(body.get("request_id") or (exc.request_id or "")),
    }


class LLMRequestError(ApiException):
    """LLM 调用异常（带调用上下文，供上层组装 error_detail）"""

    def __init__(
        self,
        message: str,
        *,
        model: str = "",
        base_url: str = "",
        status_code: int | None = None,
        upstream_code: str = "",
        upstream_message: str = "",
        request_id: str = "",
        reason: str = "",
        failed_scenes: int | None = None,
        total_scenes: int | None = None,
    ) -> None:
        super().__init__(BusinessErrorCode.VIDEO_DESCRIPTION_LLM_ERROR, message)
        # 不带错误码前缀的短原因，供上层拼接聚合消息（直接拼 message 会出现两层前缀）
        self.reason = reason
        self.model = model
        self.base_url = base_url
        self.status_code = status_code
        self.upstream_code = upstream_code
        self.upstream_message = upstream_message
        self.request_id = request_id
        self.failed_scenes = failed_scenes
        self.total_scenes = total_scenes

    def to_detail(self) -> dict:
        """结构化明细：字段缺失即省略，不回填空串，避免调用方误判。"""
        detail: dict = {}
        if self.model:
            detail["model"] = self.model
        if self.base_url:
            detail["base_url"] = redact_url(self.base_url)
        if self.status_code is not None:
            detail["status_code"] = self.status_code
        if self.upstream_code:
            detail["upstream_code"] = self.upstream_code
        if self.upstream_message:
            detail["upstream_message"] = self.upstream_message
        if self.request_id:
            detail["request_id"] = self.request_id
        if self.failed_scenes is not None:
            detail["failed_scenes"] = self.failed_scenes
        if self.total_scenes is not None:
            detail["total_scenes"] = self.total_scenes
        return detail


class LLMClient:
    """OpenAI 兼容的大模型客户端，用于场景图片描述"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout: int = 120,
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url
        # 空 api_key（V-Scheduler 网关免验证模式）：SDK 构造期强制要求凭据、请求期要求该头
        # 「存在或显式省略」，用空 provider + Omit 组合免发 Authorization 头；填假值会 401。
        self._extra_headers: dict[str, str | Omit] = {} if api_key else {"Authorization": Omit()}
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or _no_credentials,
            timeout=timeout,
            max_retries=2,
        )
        logger.info(
            "LLM client 初始化: model=%s base_url=%s key=%s",
            model_name,
            redact_url(base_url),
            f"***{api_key[-4:]}" if api_key else "(未设置)",
        )

    async def close(self) -> None:
        """关闭底层 AsyncOpenAI/httpx 客户端，避免事件循环关闭后泄漏。"""
        await self._client.close()

    async def describe_image(self, image_path: Path, scene_index: int) -> str:
        """对单张场景图片进行大模型描述

        Args:
            image_path: 图片文件路径
            scene_index: 场景序号

        Returns:
            描述文本

        Raises:
            LLMRequestError: API 调用失败
        """
        mime = _IMAGE_EXT_TO_MIME.get(image_path.suffix.lower(), "image/jpeg")
        base64_image = self._encode_image(image_path)
        image_url = f"data:{mime};base64,{base64_image}"

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": USER_PROMPT_TEMPLATE.format(scene_index=scene_index),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "low"},
                    },
                ],
            },
        ]

        try:
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                max_tokens=_MAX_TOKENS,
                temperature=0.2,
                extra_headers=self._extra_headers,
            )
        except openai.APIStatusError as exc:
            # 注意顺序：APIStatusError 必须在 APIError 之前
            up = _upstream_fields(exc)
            code_part = f" {up['code']}" if up["code"] else ""
            # str(exc) 里带整段响应 JSON，不能拼进 message（会进调用方的库和界面）
            reason = up["msg"] or f"HTTP {exc.status_code}"
            logger.error(
                "LLM 调用失败: model=%s base_url=%s status=%s code=%s request_id=%s",
                self._model_name,
                redact_url(self._base_url),
                exc.status_code,
                up["code"],
                up["request_id"],
            )
            raise LLMRequestError(
                f"模型 {self._model_name} 调用失败（HTTP {exc.status_code}{code_part}）：{reason}",
                model=self._model_name,
                base_url=self._base_url,
                status_code=exc.status_code,
                upstream_code=up["code"],
                upstream_message=up["msg"],
                request_id=up["request_id"],
                reason=reason,
            ) from exc
        except openai.APIError as exc:
            # 连接/超时/协议错误
            logger.error(
                "LLM 调用失败: model=%s base_url=%s err=%s",
                self._model_name,
                redact_url(self._base_url),
                exc,
            )
            raise LLMRequestError(
                f"模型 {self._model_name} 调用失败：{exc}",
                model=self._model_name,
                base_url=self._base_url,
                reason=str(exc),
            ) from exc

        content = response.choices[0].message.content
        if content is None or not content.strip():
            # 空 content 判为失败以触发重试，避免静默写入空描述
            finish = response.choices[0].finish_reason
            usage = response.usage.completion_tokens if response.usage else None
            empty_reason = f"返回内容为空（finish_reason={finish}, completion_tokens={usage}）"
            raise LLMRequestError(
                f"模型 {self._model_name} {empty_reason}",
                model=self._model_name,
                base_url=self._base_url,
                reason=empty_reason,
            )

        return content.strip()

    @staticmethod
    def _encode_image(image_path: Path) -> str:
        """读取图片文件并返回 Base64 编码字符串"""
        return base64.b64encode(image_path.read_bytes()).decode("utf-8")
