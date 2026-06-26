from pydantic import BaseModel, Field


class LoginCommand(BaseModel):
    username: str = Field(description="用户名", min_length=1, max_length=50)
    password: str = Field(description="密码", min_length=1, max_length=32)


class AddUserCommand(BaseModel):
    username: str = Field(description="用户名", min_length=1, max_length=50)
    password: str = Field(description="密码", min_length=1, max_length=32)


class UserDTO(BaseModel):
    id: int = Field(description="用户ID")
    username: str = Field(description="用户名")


class LoginDTO(BaseModel):
    token: str = Field(description="登录令牌")
    userId: int = Field(description="用户ID")
    username: str = Field(description="用户名")
    realName: str | None = Field(default=None, description="真实姓名")


class CurrentUser(BaseModel):
    id: int = Field(description="用户ID")
    username: str = Field(description="用户名")


class TokenPayload(BaseModel):
    userId: int = Field(description="用户ID")
    username: str = Field(description="用户名")
    iat: int = Field(description="签发时间")
    exp: int = Field(description="过期时间")
