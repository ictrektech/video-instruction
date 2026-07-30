# Video-Instruction API 文档

> 视频场景检测、结构化与大模型描述服务接口规范

| 项目 | 规范 |
|---|---|
| 版本 | v0.1.0 |
| 协议 | HTTP/1.1 |
| 框架 | FastAPI (uvicorn) |
| 响应格式 | `application/json` |
| 认证 | 无（内部服务间调用） |

---

## 目录

- [1. 概述](#1-概述)
- [2. 统一响应格式](#2-统一响应格式)
- [3. 通用错误码](#3-通用错误码)
- [4. 场景检测服务 — :8910](#4-场景检测服务--8910)
  - [4.1 健康检查 — GET /api/health](#41-健康检查--get-apihealth)
  - [4.2 场景检测任务 — POST /api/v1/scenes/detect](#42-场景检测任务--post-apiv1scenesdetect)
- [5. 视频结构化服务 — :8911](#5-视频结构化服务--8911)
  - [5.1 健康检查 — GET /api/health](#51-健康检查--get-apihealth)
  - [5.2 视频结构化 — POST /api/v1/video/structure](#52-视频结构化--post-apiv1videostructure)
- [6. 典型调用流程](#6-典型调用流程)

---

## 1. 概述

Video-Instruction 是一个无状态的视频分析服务，提供场景检测、视频结构化（帧提取 + 缩略图生成）以及基于大语言模型的场景描述能力。服务分为两个独立微服务，通过 HTTP API 协作。

### 服务架构

```
┌───────────────────────┐      ┌───────────────────────┐
│   Scene Detection     │      │      Structure        │
│      Port 8910        │      │      Port 8911         │
│                       │      │                       │
│  POST /detect  ───────┼─────>│  POST /structure      │
│                       │      │  callback multipart   │
└───────────────────────┘      └───────────────────────┘
```

### Base URL

```
场景检测:  http://scene-detection:8910
视频结构化: http://structure:8911
```

### 通信协议

| 项目 | 规范 |
|---|---|
| 传输协议 | HTTP/1.1 |
| 请求编码 | 提交接口为 `application/json`；结构化回调为 `multipart/form-data` |
| 响应编码 | 提交响应为 `application/json`；最终结果通过调用方 callback 接收 |
| 认证 | 无（内部服务间调用，不暴露到公网） |

### 端点总览

#### 场景检测服务 (8910)

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/v1/scenes/detect` | 提交视频场景边界检测任务 |
| `GET` | `/api/v1/scenes/detect/tasks/{task_id}` | 查询场景检测任务状态 |

#### 视频结构化服务 (8911)

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/v1/video/structure` | 提交视频结构化任务，状态和结果通过 callback 推送 |
| `GET` | `/api/v1/video/structure/tasks/{task_id}` | 查询视频结构化任务状态 |

---

## 2. 统一响应格式

业务接口成功时统一返回 `ResponseDTO<T>` 结构。主动抛出的业务错误（`ApiException`）也返回 HTTP 200，通过 `code` 字段区分；请求体验证错误仍由 FastAPI 返回 HTTP 422，未捕获异常返回 HTTP 500。

### 响应体结构

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": { ... }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | `int` | 业务状态码，`0` 表示成功，非零表示错误 |
| `msg` | `string` | 状态描述信息 |
| `data` | `T \| null` | 响应数据，具体结构取决于端点。错误时为 `null` |

### 成功响应

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": { ... }
}
```

### 错误响应

```json
{
  "code": 70101,
  "msg": "视频文件未找到: /data/unknown.mp4",
  "data": null
}
```

---

## 3. 通用错误码

| 业务码 | 说明 |
|---|---|
| `0` | 操作成功 |
| `10001` | 找不到资源（格式化：`找不到ID为 {id} 的 {resource}`） |
| `10002` | 不支持的操作 |
| `10003` | 批量参数 ID 列表为空 |
| `10004` | 参数校验失败 |
| `70101` | 视频文件未找到 |
| `70102` | 视频缓存未找到 |
| `70103` | 大模型调用失败 |
| `70104` | 视频场景缓存未找到，请先执行结构化 |
| `99999` | 操作失败（通用错误） |

> **注意：** 业务错误返回 HTTP 200 状态码，通过 `code` 字段区分成功与失败；请求参数校验错误和未捕获异常分别使用 FastAPI 默认的 HTTP 422/500。

---

## 4. 场景检测服务 — :8910

### 4.1 健康检查 — GET /api/health

```
GET /api/health
```

检测场景检测服务是否存活。

#### 请求参数

无

#### 响应

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | `int` | 状态码 |
| `msg` | `string` | 状态消息 |
| `data.status` | `string` | 固定为 `"ok"` |
| `data.service` | `string` | 固定为 `"scene-detection"` |

#### 响应示例

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "status": "ok",
    "service": "scene-detection"
  }
}
```

---

### 4.2 场景检测任务 — POST /api/v1/scenes/detect

```
POST /api/v1/scenes/detect
GET  /api/v1/scenes/detect/tasks/{task_id}
Content-Type: application/json
```

#### 功能说明

提交场景检测任务。服务生成唯一 `task_id` 并写入 SQLite 任务队列，接口立即返回 `queued`；实际检测在后台按并发限制执行，调用方通过 `GET /api/v1/scenes/detect/tasks/{task_id}` 查询状态和最终场景边界结果。

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `asset_id` | `string` | **必填** | — | 调用方资产 ID |
| `video_path` | `string` | **必填** | — | 视频文件路径，相对于 `data_base_path`，也支持绝对路径 |
| `threshold` | `float \| null` | 可选 | `null` | 场景检测阈值。`null` 时按视频时长策略自动选择 |
| `scale_width` | `int \| null` | 可选 | `null` | 检测管道 scale 宽度。`null` 使用服务端配置，`0` 表示不缩放 |
| `decode_threads` | `int \| null` | 可选 | `null` | ffmpeg 解码线程数。`null` 使用服务端配置，`0` 表示 ffmpeg auto |

#### 请求示例

```json
{
  "asset_id": "immich-asset-001",
  "video_path": "video/sample.mp4",
  "threshold": 30.0
}
```

#### 提交响应

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "task_id": "a0f30a58-77f7-48d3-bd0b-f5c455123456",
    "asset_id": "immich-asset-001",
    "status": "queued"
  }
}
```

#### 状态查询响应

`GET /api/v1/scenes/detect/tasks/{task_id}` 返回 `ResponseDTO<TaskStatusDTO>`。检测成功后，`data.result` 包含完整 `DetectResult`：

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "task_id": "a0f30a58-77f7-48d3-bd0b-f5c455123456",
    "asset_id": "immich-asset-001",
    "task_type": "scene_detect",
    "status": "succeeded",
    "stage": "done",
    "progress": 1.0,
    "result": {
      "metadata": {"fps": 29.97, "total_frames": 3600, "duration": 120.12, "width": 1920, "height": 1080},
      "policy": {"threshold": 30.0, "min_scene_len_sec": 5.0, "max_scene_count": 80},
      "scenes": [{"scene_index": 0, "start_frame": 0, "end_frame": 450, "start_time": 0.0, "end_time": 15.02}],
      "warnings": [],
      "elapsed_sec": 3.25
    }
  }
}
```

失败时 `data.status="failed"`，并带 `data.error` 字段。

---

## 5. 视频结构化服务 — :8911

### 5.1 健康检查 — GET /api/health

```
GET /api/health
```

检测结构化服务是否存活。

#### 请求参数

无

#### 响应

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.status` | `string` | 固定为 `"ok"` |
| `data.service` | `string` | 固定为 `"structure"` |

#### 响应示例

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "status": "ok",
    "service": "structure"
  }
}
```

---

### 5.2 视频结构化 — POST /api/v1/video/structure

```
POST /api/v1/video/structure
Content-Type: application/json
```

#### 功能说明

提交视频结构化任务。接口会先检查 `callback_url` 是否可达，再由服务生成唯一 `task_id` 并写入 SQLite 任务队列，返回 `queued`；实际处理在服务后台按并发限制执行，任务状态与最终结果通过调用方提供的 `callback_url` 以 `multipart/form-data` 推送。

**前置条件：** 必须先调用场景检测服务获取 `scenes` 列表。

结构化服务不保存第三方业务产物，也不提供结构化结果缓存。场景图片只在本次任务的临时目录中生成，成功 callback 完成或任务结束后由服务清理。调用方负责接收、持久化和管理图片生命周期。

#### 执行流水线

```
Step 0: 接收任务 → 写入 SQLite 队列 → 返回 queued
Step 1: ffprobe 提取视频元数据（fps/分辨率/编码/时长）
Step 2: 接收场景边界（来自场景检测服务的 scenes 数组）
Step 3: 每场景采样 grid_rows×grid_cols 帧 → ffmpeg 提取 → PIL 拼接到临时目录
Step 4: multipart/form-data callback 推送 succeeded 或 failed
```

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `asset_id` | `string` | **必填** | — | 调用方资产 ID |
| `callback_url` | `string` | **必填** | — | 接收结构化状态和结果的 callback URL |
| `video_path` | `string` | **必填** | — | 视频文件路径，相对于 `data_base_path` |
| `scenes` | `SceneBoundaryInput[]` | **必填** | — | 场景边界列表，由场景检测服务提供 |
| `scenes[].scene_index` | `int` | 可选 | `0` | 场景序号（从 0 开始） |
| `scenes[].start_frame` | `int` | **必填** | — | 起始帧索引 |
| `scenes[].end_frame` | `int` | **必填** | — | 结束帧索引 |
| `scenes[].start_time` | `float` | 可选 | `0.0` | 起始时间（秒） |
| `scenes[].end_time` | `float` | 可选 | `0.0` | 结束时间（秒） |
| `frame_grid` | `bool` | 可选 | `true` | **缩略图总开关**。`false` 则跳过缩略图生成，只返回场景边界 |
| `grid_rows` | `int` | 可选 | `1` | 每场景缩略图拼接行数。默认单帧；如需九宫格可设为 `3` |
| `grid_cols` | `int` | 可选 | `1` | 每场景缩略图拼接列数。默认单帧；如需九宫格可设为 `3` |

> **采样策略：** 帧采样时跳过场景首尾各 5%（避免转场过渡帧），在中间 90% 区间内均匀采样。单帧模式取区间正中间位置。

> **单格大小限制：** 服务端通过 `video_grid_tile_max_height`（默认 360px）控制缩放后单格最大高度。

> **取帧超时：** 单次 ffmpeg 取帧默认 60 秒超时，可通过 `video_ffmpeg_timeout` 配置调整；超时或取帧失败会在对应场景返回 `grid_failed` warning。

#### 请求示例

**生成 3×3 九宫格：**

```http
POST /api/v1/video/structure HTTP/1.1
Content-Type: application/json

{
  "asset_id": "immich-asset-001",
  "callback_url": "http://immich_server:3001/api/video-structure/callback",
  "video_path": "video/sample.mp4",
  "scenes": [
    {
      "scene_index": 0,
      "start_frame": 0,
      "end_frame": 450,
      "start_time": 0.0,
      "end_time": 15.02
    },
    {
      "scene_index": 1,
      "start_frame": 451,
      "end_frame": 980,
      "start_time": 15.05,
      "end_time": 32.70
    }
  ],
  "grid_rows": 3,
  "grid_cols": 3
}
```

**只提取每场景中间单帧（默认）：**

```http
POST /api/v1/video/structure HTTP/1.1
Content-Type: application/json

{
  "asset_id": "immich-asset-001",
  "callback_url": "http://immich_server:3001/api/video-structure/callback",
  "video_path": "video/sample.mp4",
  "scenes": [
    {
      "scene_index": 0,
      "start_frame": 0,
      "end_frame": 450,
      "start_time": 0.0,
      "end_time": 15.02
    }
  ]
}
```

**仅返回场景边界，不生成缩略图：**

```http
POST /api/v1/video/structure HTTP/1.1
Content-Type: application/json

{
  "asset_id": "immich-asset-001",
  "callback_url": "http://immich_server:3001/api/video-structure/callback",
  "video_path": "video/sample.mp4",
  "scenes": [...],
  "frame_grid": false
}
```

#### 响应参数

**`data` 字段结构：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.task_id` | `string` | 服务生成的任务 ID |
| `data.asset_id` | `string` | 调用方资产 ID |
| `data.status` | `string` | 固定为 `queued`，表示服务已接收并入队 |

#### Callback 事件

结构化服务会向 `callback_url` POST `multipart/form-data`。每次回调都包含一个 `event` part：

```json
{
  "task_id": "a0f30a58-77f7-48d3-bd0b-f5c455123456",
  "asset_id": "immich-asset-001",
  "status": "running",
  "stage": "structure",
  "progress": 0.0,
  "message": "structure task started"
}
```

成功时，`event.status="succeeded"`，`event.result` 为结构化结果；场景图片作为二进制 file part 传输：

| part | 类型 | 说明 |
|---|---|---|
| `event` | `application/json` | 状态、元数据、场景结构化结果 |
| `scene_001` | `image/jpeg` | 第 1 个场景图 |
| `scene_002` | `image/jpeg` | 第 2 个场景图 |

`event.result.scenes[].grid_image` 为文件名，如 `scene_001.jpg`；调用方根据 scene_index 或 part 名保存图片。

失败时，`event.status="failed"`，并带 `error`：

```json
{
  "task_id": "a0f30a58-77f7-48d3-bd0b-f5c455123456",
  "asset_id": "immich-asset-001",
  "status": "failed",
  "stage": "structure",
  "error": {
    "code": "70101",
    "message": "视频文件未找到: /photos/upload/demo.mp4",
    "detail": ""
  }
}
```

#### 成功结果字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `result.video_hash` | `string` | 视频内容 MD5 哈希（快速采样） |
| `result.metadata` | `object` | 视频元数据 |
| `result.metadata.video_path` | `string` | 视频文件相对路径 |
| `result.metadata.fps` | `float` | 帧率 |
| `result.metadata.duration` | `float` | 时长（秒） |
| `result.metadata.width` | `int` | 视频宽度（像素） |
| `result.metadata.height` | `int` | 视频高度（像素） |
| `result.metadata.codec` | `string` | 视频编码格式 |
| `result.metadata.bitrate` | `int` | 比特率（bps） |
| `result.metadata.has_audio` | `bool` | 是否包含音频流 |
| `result.metadata.total_frames` | `int` | 总帧数 |
| `result.grid_base_path` | `string` | 空字符串；图片通过 multipart file part 传输 |
| `result.scenes` | `SceneDTO[]` | 场景列表 |
| `result.scenes[].scene_id` | `string` | 场景唯一 ID（8 位十六进制） |
| `result.scenes[].scene_index` | `int` | 场景序号（从 0 开始） |
| `result.scenes[].start_time` | `float` | 起始时间（秒） |
| `result.scenes[].end_time` | `float` | 结束时间（秒） |
| `result.scenes[].start_frame` | `int` | 起始帧索引 |
| `result.scenes[].end_frame` | `int` | 结束帧索引 |
| `result.scenes[].grid_image` | `string \| null` | 缩略图文件名（如 `scene_001.jpg`）。`frame_grid=false` 时为 `null` |
| `result.warnings` | `WarningDTO[]` | 警告信息列表 |
| `result.stage_timings` | `object` | 各阶段耗时（秒） |
| `result.stage_timings.metadata` | `float` | 元数据提取耗时 |
| `result.stage_timings.frame_grid` | `float` | 缩略图生成耗时（仅 `frame_grid=true` 时存在） |
| `result.stage_timings.total` | `float` | 总耗时 |
| `result.elapsed_sec` | `float` | 总耗时（秒），与 `stage_timings.total` 一致 |

#### 提交响应示例

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "task_id": "a0f30a58-77f7-48d3-bd0b-f5c455123456",
    "asset_id": "immich-asset-001",
    "status": "queued"
  }
}
```

#### 状态查询响应

`GET /api/v1/video/structure/tasks/{task_id}` 返回 `ResponseDTO<TaskStatusDTO>`，用于调试和容错。查询结果可包含 `queued`、`running`、`succeeded`、`failed` 状态；成功结果中的图片仍只通过 callback 的 file part 交付，不由查询接口承载。

---

### 5.3 已移除接口

以下接口已从当前 dev 设计中移除：

- `POST /api/v1/video/describe`
- `DELETE /api/v1/video/cache`
- `GET /api/v1/video/storage`
- `/api/v2/*/jobs` 查询式异步任务 API

结构化服务不再管理第三方派生产物的长期存储；调用方通过 callback 接收图片并自行持久化。

---

## 6. 典型调用流程

### 完整流水线（场景检测查询 → 结构化 callback）

```
调用方                          Scene-Detect (:8910)       Structure (:8911)
  │                                    │                        │
  │  1. 场景检测                        │                        │
  ├───────────────────────────────────>│                        │
  │  POST /api/v1/scenes/detect        │                        │
  │  { asset_id, video_path }                                   │
  │<───────────────────────────────────┤                        │
  │  { task_id, asset_id, status: queued }                      │
  │  GET /api/v1/scenes/detect/tasks/{task_id}                  │
  │<───────────────────────────────────┤                        │
  │  { status: succeeded, result: { scenes } }                  │
  │                                    │                        │
  │  2. 视频结构化                       │                        │
  ├────────────────────────────────────────────────────────────>│
  │  POST /api/v1/video/structure                                │
  │  { asset_id, video_path, scenes, callback_url }             │
  │<────────────────────────────────────────────────────────────┤
  │  { task_id, asset_id, status: queued }                      │
  │                                    │                        │
  │  3. 状态/结果回调                     │                        │
  │<────────────────────────────────────────────────────────────┤
  │  multipart/form-data: event + scene_001.jpg + ...           │
```

### 产物生命周期说明

- **场景检测不缓存** — 每次请求都重新检测。
- **结构化不缓存** — 服务只在任务临时目录中生成场景图，成功或失败后清理。
- **调用方管理产物** — Immich 或其他调用方通过 multipart callback 接收图片，并自行保存、删除、备份和迁移。
- **无缓存目录契约** — 当前 dev 设计不再暴露 `/api/v1/video/storage`，也不要求挂载 `/data/video-structure-cache`。

### 任务队列说明

- **任务状态存储** — SQLite，默认 `TASK_DB_PATH=/app/data/tasks/tasks.db`。
- **最大并发** — `TASK_MAX_CONCURRENCY`，默认 `2`，按任务类型分别限制。
- **队列上限** — `TASK_QUEUE_LIMIT`，默认 `20`；超过上限时提交接口返回业务错误。
- **结果 TTL** — `TASK_RESULT_TTL_SEC`，默认 `3600` 秒。`running` 任务不会被 TTL 强制中断；任务结束时若已超过 TTL，结果直接丢弃。
- **终态查询即消费** — `succeeded` / `failed` 状态被 `GET /tasks/{task_id}` 成功返回后立即删除；后续查询返回任务不存在。
- **重启不续跑** — 服务启动时会清理本服务类型遗留的 `queued` / `running` 任务；调用方收到 404 后重新提交。
- **结构化 callback 重试** — `CALLBACK_RETRY_ATTEMPTS` 默认 `3`，`CALLBACK_RETRY_DELAY_SEC` 默认 `1` 秒，按指数退避重试。

### 容器挂载建议

```
${UPLOAD_LOCATION}/photos:/photos:ro
../data:/app/data
```

---

*基于 video-instruction v0.1.0 源码分析生成 · 2026-07-29*
