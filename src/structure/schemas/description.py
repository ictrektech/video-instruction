from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from structure.schemas.model_config import ModelConfig
from structure.schemas.video import WarningDTO


class DescribeSceneCommand(BaseModel):
    """场景描述请求参数"""

    structure_job_id: str = Field(
        description="structure job ID，describe 按该 job 的 staging 目录读取 grids"
    )
    force: bool = Field(default=False, description="强制重新描述，忽略已有描述")
    model_cfg: ModelConfig | None = Field(
        default=None,
        description="大模型配置，不传则使用服务端 settings 默认值",
    )


class SceneDescriptionItem(BaseModel):
    """单个场景描述结果"""

    scene_index: int = Field(description="场景序号（从 0 开始）")
    grid_image: str = Field(description="九宫格图片文件名，如 scene_001.jpg")
    description: str = Field(default="", description="大模型生成的场景描述文本")
    status: Literal["ok", "skipped", "failed"] = Field(description="描述状态")
    error: str | None = Field(default=None, description="失败时的错误信息")


class SceneDescriptionResult(BaseModel):
    """场景描述结果"""

    structure_job_id: str = Field(description="对应 structure job ID")
    video_hash: str = Field(default="", description="视频内容哈希（MD5），来自 staging manifest")
    descriptions: list[SceneDescriptionItem] = Field(description="场景描述列表")
    warnings: list[WarningDTO] = Field(default_factory=list, description="警告信息")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> Literal["completed", "partial"]:
        """整体状态：全部场景成功/跳过为 completed，存在失败为 partial。"""
        return "partial" if any(i.status == "failed" for i in self.descriptions) else "completed"
