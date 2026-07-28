# Review Notes

## 场景描述失败结果被缓存，导致后续不再调用 LLM

### 现象

`POST /api/v1/video/describe` 首次调用 LLM 失败后，服务仍然生成
`_descriptions.json`，其中每个场景的状态为 `failed`：

```json
{
  "scene_index": 0,
  "grid_image": "scene_001.jpg",
  "description": "",
  "status": "failed",
  "error": "大模型调用失败: Connection error."
}
```

后续再次调用 `/api/v1/video/describe` 时，如果没有传 `force=true`，服务会直接命中
`_descriptions.json` 并返回失败缓存，不再重新调用 LLM。

### 复现信息

- 视频 hash: `39da8b9e0f7204322e8a0bc0e5578945`
- 结构化缓存: `scenes/39da8b9e0f7204322e8a0bc0e5578945/_cached.json`
- 描述缓存: `scenes/39da8b9e0f7204322e8a0bc0e5578945/_descriptions.json`
- 缓存内容中两个场景均为 `status=failed`
- 错误信息: `大模型调用失败: Connection error.`

### 根因

`structure.services.video.description.describe_scenes()` 在 `force=false` 时只判断
`_descriptions.json` 是否存在且可解析：

```python
cached_descriptions = _load_cached_descriptions(cache_dir)
if cached_descriptions is not None:
    return cached_descriptions
```

当前逻辑没有区分缓存中的描述是否成功。如果上一次 LLM 调用因为网络或模型服务异常失败，
失败结果也会作为有效缓存返回。

### 影响

- 临时网络错误、模型服务重启、模型不可达等瞬时故障会被持久化。
- 用户再次请求描述时看起来接口成功返回 `200`，但实际不会重试 LLM。
- `LLM_TRACE_LOG=true` 时也看不到新的 LLM 交互日志，因为请求在创建 `LLMClient` 之前已经返回。

### 建议修复

不要把全失败的描述结果当作有效缓存。可选方案：

1. 缓存命中时检查是否存在 `status="ok"` 的描述；如果全部失败，则忽略缓存并重新生成。
2. 新增请求参数或配置项控制是否允许返回失败缓存。
3. 保存 `_descriptions.json` 时只在至少一个场景成功时写缓存；全失败时不落盘。
4. 对部分失败场景支持增量重试：已有 `ok` 的场景复用缓存，`failed` 的场景重新调用 LLM。

短期绕过方式：调用 `/api/v1/video/describe` 时传 `force=true`，强制重新调用 LLM。
