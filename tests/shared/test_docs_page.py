"""内置文档页面（/doc/integration.html）静态挂载测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.utils.docs_page import mount_docs


def test_mount_docs_serves_page() -> None:
    app = FastAPI()
    mount_docs(app)
    resp = TestClient(app).get("/doc/integration.html")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Video Instruction" in resp.text
