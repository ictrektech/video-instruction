from logging import getLogger

from fastapi import APIRouter

from shared.schemas.common.response import ResponseDTO
from structure.core.settings import settings
from structure.schemas.description import (
    DescribeSceneCommand,
    SceneDescriptionResult,
)
from structure.services.video import description as description_service

logger = getLogger(__name__)
router = APIRouter()


@router.post(
    "/describe",
    response_model=ResponseDTO[SceneDescriptionResult],
    summary="场景图片大模型描述",
    description="传入 video_hash，读取已缓存的场景拼图，对各场景调用大模型生成描述文本。",
)
async def describe_scenes(
    command: DescribeSceneCommand,
) -> ResponseDTO[SceneDescriptionResult]:
    """对已结构化的视频场景进行大模型描述。"""
    result = await description_service.describe_scenes(
        video_hash=command.video_hash,
        settings=settings,
        force=command.force,
        model_cfg=command.model_cfg,
    )
    logger.info("视频 %s 场景描述完成", result.video_hash)
    return ResponseDTO.ok(result)
