from datetime import datetime

from sqlmodel import Field, SQLModel


class BaseMixin(SQLModel):
    create_time: datetime | None = Field(default=None, description="创建时间")
    update_time: datetime | None = Field(default=None, description="更新时间")
    deleted: bool = Field(default=False, description="是否删除")
