from scene_detect.api.routes import router


def test_scene_detect_exposes_only_sync_v1_routes():
    paths = {route.path for route in router.routes}

    assert "/api/v1/scenes/detect" in paths
    assert not any(path.startswith("/v2/") for path in paths)
