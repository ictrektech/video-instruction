from __future__ import annotations

import base64
import logging
from pathlib import Path
from time import perf_counter

import openai
from openai.types.chat import ChatCompletionMessageParam

from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
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
        trace_log: bool = False,
    ) -> None:
        self._base_url = base_url
        self._model_name = model_name
        self._trace_log = trace_log
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=2,
        )

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
        prompt = USER_PROMPT_TEMPLATE.format(scene_index=scene_index)

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "low"},
                    },
                ],
            },
        ]

        started_at = perf_counter()
        if self._trace_log:
            logger.info(
                "LLM 请求: model=%s base_url=%s scene_index=%d image_path=%s mime=%s prompt=%s",
                self._model_name,
                self._base_url,
                scene_index,
                image_path,
                mime,
                prompt,
            )

        try:
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                max_tokens=256,
                temperature=0.2,
            )
        except openai.APIError as exc:
            elapsed_sec = perf_counter() - started_at
            if self._trace_log:
                logger.error(
                    "LLM 错误: model=%s base_url=%s scene_index=%d image_path=%s mime=%s "
                    "prompt=%s error=%s elapsed_sec=%.3f",
                    self._model_name,
                    self._base_url,
                    scene_index,
                    image_path,
                    mime,
                    prompt,
                    exc,
                    elapsed_sec,
                )
            else:
                logger.error("LLM 调用失败: %s", exc)
            raise LLMRequestError(str(exc)) from exc

        content = response.choices[0].message.content
        if content is None:
            elapsed_sec = perf_counter() - started_at
            if self._trace_log:
                logger.error(
                    "LLM 错误: model=%s base_url=%s scene_index=%d image_path=%s mime=%s "
                    "prompt=%s error=%s elapsed_sec=%.3f",
                    self._model_name,
                    self._base_url,
                    scene_index,
                    image_path,
                    mime,
                    prompt,
                    "模型返回内容为空",
                    elapsed_sec,
                )
            raise LLMRequestError("模型返回内容为空")

        description = content.strip()
        if self._trace_log:
            elapsed_sec = perf_counter() - started_at
            logger.info(
                "LLM 响应: model=%s base_url=%s scene_index=%d image_path=%s mime=%s "
                "prompt=%s response=%s elapsed_sec=%.3f",
                self._model_name,
                self._base_url,
                scene_index,
                image_path,
                mime,
                prompt,
                description,
                elapsed_sec,
            )

        return description

    @staticmethod
    def _encode_image(image_path: Path) -> str:
        """读取图片文件并返回 Base64 编码字符串"""
        return base64.b64encode(image_path.read_bytes()).decode("utf-8")
