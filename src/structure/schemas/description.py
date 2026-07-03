from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from structure.schemas.video import WarningDTO


class DescribeSceneCommand(BaseModel):
    """场景描述请求参数"""

    video_hash: str = Field(description="视频内容哈希（MD5）")
    force: bool = Field(default=False, description="强制重新描述，忽略缓存")


class SceneDescriptionItem(BaseModel):
    """单个场景描述结果"""

    scene_index: int = Field(description="场景序号（从 0 开始）")
    grid_image: str = Field(description="九宫格图片文件名，如 scene_001.jpg")
    description: str = Field(default="", description="大模型生成的场景描述文本")
    status: Literal["ok", "skipped", "failed"] = Field(description="描述状态")
    error: str | None = Field(default=None, description="失败时的错误信息")


class SceneDescriptionResult(BaseModel):
    """场景描述结果"""

    video_hash: str = Field(description="视频内容哈希（MD5）")
    descriptions: list[SceneDescriptionItem] = Field(description="场景描述列表")
    warnings: list[WarningDTO] = Field(default_factory=list, description="警告信息")
