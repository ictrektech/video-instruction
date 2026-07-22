from pathlib import Path

from fastapi import APIRouter

from shared.schemas.common.response import ResponseDTO
from structure.core.settings import settings

router = APIRouter()


@router.get(
    "/storage",
    summary="存储路径查询",
    description="返回 data_base_path、cache_base_path、scenes 缓存目录绝对路径。",
)
async def get_storage_info() -> ResponseDTO[dict[str, str]]:
    """获取 data_base_path、cache_base_path、scenes 缓存目录"""
    scenes_root = Path(settings.cache_base_path) / settings.video_scenes_dir
    return ResponseDTO.ok(
        {
            "data_base_path": str(Path(settings.data_base_path).resolve()),
            "cache_base_path": str(Path(settings.cache_base_path).resolve()),
            "scenes_path": str(scenes_root.resolve()),
        }
    )
