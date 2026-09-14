from __future__ import annotations

import base64
import logging
from pathlib import Path

import openai
from openai.types.chat import ChatCompletionMessageParam

from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.utils.video_source import redact_url
from structure.services.llm.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


_IMAGE_EXT_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class LLMRequestError(ApiException):
    """LLM 调用异常"""

    def __init__(self, message: str) -> None:
        super().__init__(BusinessErrorCode.VIDEO_DESCRIPTION_LLM_ERROR, message)


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
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
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
                max_tokens=256,
                temperature=0.2,
            )
        except openai.APIError as exc:
            logger.error("LLM 调用失败: %s", exc)
            raise LLMRequestError(str(exc)) from exc

        content = response.choices[0].message.content
        if content is None:
            raise LLMRequestError("模型返回内容为空")

        return content.strip()

    @staticmethod
    def _encode_image(image_path: Path) -> str:
        """读取图片文件并返回 Base64 编码字符串"""
        return base64.b64encode(image_path.read_bytes()).decode("utf-8")
