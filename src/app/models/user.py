from sqlmodel import Field

from app.models.mixins.base import BaseMixin


class User(BaseMixin, table=True):
    __tablename__ = "sys_user"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True, description="用户ID")
    username: str = Field(index=True, max_length=50, description="用户名")
    password: str = Field(max_length=64, description="密码")
    real_name: str | None = Field(default=None, max_length=50, description="真实姓名")
    email: str | None = Field(default=None, max_length=100, description="邮箱")
    phone: str | None = Field(default=None, max_length=20, description="手机号")
    status: int = Field(default=1, description="用户状态")
