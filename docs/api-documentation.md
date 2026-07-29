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
  - [4.2 场景检测 — POST /api/v1/scenes/detect](#42-场景检测--post-apiv1scenesdetect)
- [5. 视频结构化服务 — :8911](#5-视频结构化服务--8911)
  - [5.1 健康检查 — GET /api/health](#51-健康检查--get-apihealth)
  - [5.2 视频结构化 — POST /api/v1/video/structure](#52-视频结构化--post-apiv1videostructure)
  - [5.3 场景描述 — POST /api/v1/video/describe](#53-场景描述--post-apiv1videodescribe)
  - [5.4 清除缓存 — DELETE /api/v1/video/cache](#54-清除缓存--delete-apiv1videocache)
  - [5.5 存储路径 — GET /api/v1/video/storage](#55-存储路径--get-apiv1videostorage)
  - [5.6 异步任务 API — /api/v2/*/jobs](#56-异步任务-api--apiv2jobs)
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
│                       │      │  POST /describe       │
│                       │      │  DELETE /cache        │
│                       │      │  GET /storage         │
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
| 请求编码 | `application/json`（所有端点为 JSON body，无 multipart） |
| 响应编码 | `application/json` |
| 认证 | 无（内部服务间调用，不暴露到公网） |

### 端点总览

#### 场景检测服务 (8910)

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/v1/scenes/detect` | 视频场景边界检测 |
| `POST` | `/api/v2/scenes/detect/jobs` | 提交场景检测异步任务 |
| `GET` | `/api/v2/scenes/detect/jobs/{job_id}` | 查询场景检测任务状态 |

#### 视频结构化服务 (8911)

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/v1/video/structure` | 视频结构化（元数据提取 + 缩略图生成） |
| `POST` | `/api/v1/video/describe` | 场景大模型描述 |
| `DELETE` | `/api/v1/video/cache` | 清除视频缓存 |
| `GET` | `/api/v1/video/storage` | 查询存储路径 |
| `POST` | `/api/v2/video/structure/jobs` | 提交视频结构化异步任务 |
| `GET` | `/api/v2/video/structure/jobs/{job_id}` | 查询视频结构化任务状态 |
| `POST` | `/api/v2/video/describe/jobs` | 提交场景描述异步任务 |
| `GET` | `/api/v2/video/describe/jobs/{job_id}` | 查询场景描述任务状态 |

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

### 4.2 场景检测 — POST /api/v1/scenes/detect

```
POST /api/v1/scenes/detect
Content-Type: application/json
```

#### 功能说明

对视频文件执行场景边界检测。使用 PySceneDetect 的 `ContentDetector` 算法（基于帧间内容差异），通过自定义 ffmpeg 单线程解码器逐帧分析，识别场景切换点。返回每个场景的起止帧号和时间戳。

#### 执行流程

```
FfmpegVideoStream (单线程 ffmpeg rawvideo 管道)
  → PySceneDetect ContentDetector (自适应阈值)
  → 场景边界列表 [{start_frame, end_frame, start_time, end_time}]
  → 检测失败时回退为单个完整场景
```

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `video_path` | `string` | **必填** | 视频文件路径。相对于 `data_base_path`（默认 `/data/video-structured`），也支持绝对路径 |
| `threshold` | `float \| null` | 可选 | 场景切换检测阈值，越大越不敏感。未传时按视频时长策略自动选择 |
| `max_scenes` | `int \| null` | 可选 | 最大场景数限制，超出时压缩。未传时按视频时长策略自动选择 |
| `scale_width` | `int \| null` | 可选 | 检测管道缩放宽度，默认使用服务端配置（`640`），`0` 表示不缩放 |
| `decode_threads` | `int \| null` | 可选 | ffmpeg 解码线程数，默认使用服务端配置（`2`），`0` 表示 ffmpeg auto |

#### 请求示例

```http
POST /api/v1/scenes/detect HTTP/1.1
Content-Type: application/json

{
  "video_path": "video/sample.mp4",
  "threshold": 30.0,
  "max_scenes": 50
}
```

#### 响应参数

**`data` 字段结构：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.metadata` | `object` | 视频元信息 |
| `data.metadata.fps` | `float` | 帧率 |
| `data.metadata.total_frames` | `int` | 总帧数 |
| `data.metadata.duration` | `float` | 视频时长（秒） |
| `data.metadata.width` | `int` | 视频宽度（像素） |
| `data.metadata.height` | `int` | 视频高度（像素） |
| `data.policy` | `object` | 本次检测实际生效的策略参数 |
| `data.policy.threshold` | `float` | 实际使用的场景检测阈值 |
| `data.policy.min_scene_len_sec` | `float` | 短场景合并阈值（秒） |
| `data.policy.max_scene_count` | `int` | 实际使用的最大场景数 |
| `data.scenes` | `SceneBoundary[]` | 场景边界数组 |
| `data.scenes[].scene_index` | `int` | 场景序号（从 0 开始） |
| `data.scenes[].start_frame` | `int` | 起始帧索引 |
| `data.scenes[].end_frame` | `int` | 结束帧索引 |
| `data.scenes[].start_time` | `float` | 起始时间（秒） |
| `data.scenes[].end_time` | `float` | 结束时间（秒） |
| `data.warnings` | `WarningDTO[]` | 警告信息列表 |
| `data.elapsed_sec` | `float` | 检测总耗时（秒） |

#### 响应示例

**检测到多个场景：**

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "metadata": {
      "fps": 29.97,
      "total_frames": 3600,
      "duration": 120.12,
      "width": 1920,
      "height": 1080
    },
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
      },
      {
        "scene_index": 2,
        "start_frame": 981,
        "end_frame": 1499,
        "start_time": 32.73,
        "end_time": 50.05
      }
    ],
    "warnings": [],
    "elapsed_sec": 3.25
  }
}
```

**检测失败回退为单场景：**

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "metadata": {
      "fps": 25.0,
      "total_frames": 1500,
      "duration": 60.0,
      "width": 1280,
      "height": 720
    },
    "scenes": [
      {
        "scene_index": 0,
        "start_frame": 0,
        "end_frame": 1499,
        "start_time": 0.0,
        "end_time": 60.0
      }
    ],
    "warnings": [
      {
        "code": "scene_detect_fallback",
        "message": "场景检测失败，使用全视频作为单个场景",
        "scope": "scenes",
        "target_id": ""
      }
    ],
    "elapsed_sec": 1.45
  }
}
```

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

对视频执行结构化处理流水线：提取元数据 → 场景帧采样 → 缩略图拼接 → 缓存持久化。

**前置条件：** 必须先调用场景检测服务获取 `scenes` 列表。

默认流程会先从缓存检查是否已处理过同一视频（基于内容哈希 MD5），命中则直接返回。对于每帧缩略图，使用单线程 ffmpeg 在场景时间范围内 seek 提取（避免全解码），然后通过 PIL 拼接为网格图。

#### 执行流水线

```
Step 0: 计算视频 MD5 哈希（3×16KB 快速采样） → 检查缓存
Step 1: ffprobe 提取视频元数据（fps/分辨率/编码/时长）
Step 2: 接收场景边界（来自场景检测服务的 scenes 数组）
Step 3: 每场景采样 grid_rows×grid_cols 帧 → ffmpeg 提取 → PIL 拼接 → 持久化到缓存
Step 4: 缓存写入（失败仅记录日志）
```

当 `cache_enabled=false` 时，流程仍会计算视频哈希，但不会读取、清理或写入结构化缓存；缩略图仅作为临时文件参与本次响应，不会持久化到 `scenes/{video_hash}/grids/`。

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
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
| `force` | `bool` | 可选 | `false` | 强制重新处理，忽略已有缓存 |
| `cache_enabled` | `bool` | 可选 | `true` | 是否启用结构化缓存读写。`false` 时不读缓存、不清缓存、不写缓存 |

> **采样策略：** 帧采样时跳过场景首尾各 5%（避免转场过渡帧），在中间 90% 区间内均匀采样。单帧模式取区间正中间位置。

> **单格大小限制：** 服务端通过 `video_grid_tile_max_height`（默认 360px）控制缩放后单格最大高度。

> **取帧超时：** 单次 ffmpeg 取帧默认 60 秒超时，可通过 `video_ffmpeg_timeout` 配置调整；超时或取帧失败会在对应场景返回 `grid_failed` warning。

#### 请求示例

**生成 3×3 九宫格：**

```http
POST /api/v1/video/structure HTTP/1.1
Content-Type: application/json

{
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
  "video_path": "video/sample.mp4",
  "scenes": [...],
  "frame_grid": false
}
```

**关闭结构化缓存：**

```http
POST /api/v1/video/structure HTTP/1.1
Content-Type: application/json

{
  "video_path": "video/sample.mp4",
  "scenes": [...],
  "cache_enabled": false
}
```

关闭缓存后，`data.grid_base_path` 返回空字符串；即使 `frame_grid=true`，生成的缩略图也不会写入持久化缓存目录。

#### 响应参数

**`data` 字段结构：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.video_hash` | `string` | 视频内容 MD5 哈希（快速采样） |
| `data.metadata` | `object` | 视频元数据 |
| `data.metadata.video_path` | `string` | 视频文件相对路径 |
| `data.metadata.fps` | `float` | 帧率 |
| `data.metadata.duration` | `float` | 时长（秒） |
| `data.metadata.width` | `int` | 视频宽度（像素） |
| `data.metadata.height` | `int` | 视频高度（像素） |
| `data.metadata.codec` | `string` | 视频编码格式 |
| `data.metadata.bitrate` | `int` | 比特率（bps） |
| `data.metadata.has_audio` | `bool` | 是否包含音频流 |
| `data.metadata.total_frames` | `int` | 总帧数 |
| `data.grid_base_path` | `string` | 缩略图基础路径。与 `scene.grid_image` 拼接得到相对路径 |
| `data.scenes` | `SceneDTO[]` | 场景列表 |
| `data.scenes[].scene_id` | `string` | 场景唯一 ID（8 位十六进制） |
| `data.scenes[].scene_index` | `int` | 场景序号（从 0 开始） |
| `data.scenes[].start_time` | `float` | 起始时间（秒） |
| `data.scenes[].end_time` | `float` | 结束时间（秒） |
| `data.scenes[].start_frame` | `int` | 起始帧索引 |
| `data.scenes[].end_frame` | `int` | 结束帧索引 |
| `data.scenes[].grid_image` | `string \| null` | 缩略图文件名（如 `scene_001.jpg`）。`frame_grid=false` 时为 `null` |
| `data.warnings` | `WarningDTO[]` | 警告信息列表 |
| `data.stage_timings` | `object` | 各阶段耗时（秒） |
| `data.stage_timings.metadata` | `float` | 元数据提取耗时 |
| `data.stage_timings.frame_grid` | `float` | 缩略图生成耗时（仅 `frame_grid=true` 时存在） |
| `data.stage_timings.total` | `float` | 总耗时 |
| `data.elapsed_sec` | `float` | 总耗时（秒），与 `stage_timings.total` 一致 |

#### 响应示例

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "video_hash": "a1b2c3d4e5f67890",
    "metadata": {
      "video_path": "video/sample.mp4",
      "fps": 29.97,
      "duration": 120.12,
      "width": 1920,
      "height": 1080,
      "codec": "h264",
      "bitrate": 5000000,
      "has_audio": true,
      "total_frames": 3600
    },
    "grid_base_path": "scenes/a1b2c3d4e5f67890/grids/",
    "scenes": [
      {
        "scene_id": "a1b2c3d4",
        "scene_index": 0,
        "start_time": 0.0,
        "end_time": 15.02,
        "start_frame": 0,
        "end_frame": 450,
        "grid_image": "scene_001.jpg"
      },
      {
        "scene_id": "e5f67890",
        "scene_index": 1,
        "start_time": 15.05,
        "end_time": 32.70,
        "start_frame": 451,
        "end_frame": 980,
        "grid_image": "scene_002.jpg"
      }
    ],
    "warnings": [],
    "stage_timings": {
      "metadata": 0.123,
      "frame_grid": 1.890,
      "total": 2.013
    },
    "elapsed_sec": 2.01
  }
}
```

---

### 5.3 场景描述 — POST /api/v1/video/describe

```
POST /api/v1/video/describe
Content-Type: application/json
```

#### 功能说明

对已结构化的视频，读取每场景的缩略图（grid image），调用视觉大模型（Vision-Language Model）生成场景的文字描述。

**前置条件：** 必须先调用 `POST /api/v1/video/structure` 完成结构化并生成缩略图。通过 `video_hash` 查找已缓存的结构化结果。

#### 执行流程

```
Step 1: 通过 video_hash 定位缓存，确认视频已结构化
Step 2: 检查描述缓存 (_descriptions.json)，命中则直接返回（force=false 时）
Step 3: 并发对每场景缩略图调用 LLM (asyncio.Semaphore 控制并发数)
Step 4: 保存描述结果，按 scene_index 排序后返回
```

> **容错机制：** 缩略图不存在或单场景 LLM 调用失败时标记为 `failed`，不会阻塞其他场景。

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `video_hash` | `string` | **必填** | — | 视频内容 MD5 哈希，由结构化接口返回 |
| `force` | `bool` | 可选 | `false` | 强制重新描述，忽略已有描述缓存 |
| `model_cfg` | `object \| null` | 运行时必填 | `null` | 大模型配置。不传或为 `null` 会返回参数错误 |
| `model_cfg.base_url` | `string` | **必填** | — | LLM API 地址（OpenAI 兼容接口） |
| `model_cfg.api_key` | `string` | 可选 | `""` | API Key |
| `model_cfg.model_name` | `string` | **必填** | — | 模型名称，如 `gpt-4o`、`qwen2-vl-7b`、`minicpm-v` |
| `model_cfg.max_concurrency` | `int` | 可选 | `5` | 并发调用 LLM 的最大场景数 |
| `model_cfg.request_timeout` | `int` | 可选 | `120` | 单次 LLM 请求超时秒数 |

#### 请求示例

**基本请求：**

```http
POST /api/v1/video/describe HTTP/1.1
Content-Type: application/json

{
  "video_hash": "a1b2c3d4e5f67890",
  "model_cfg": {
    "base_url": "http://10.144.144.232:21436/v1",
    "api_key": "sk-fake",
    "model_name": "minicpm-v:latest",
    "max_concurrency": 10
  }
}
```

**强制重新生成：**

```http
POST /api/v1/video/describe HTTP/1.1
Content-Type: application/json

{
  "video_hash": "a1b2c3d4e5f67890",
  "force": true,
  "model_cfg": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-xxx",
    "model_name": "gpt-4o",
    "max_concurrency": 5,
    "request_timeout": 120
  }
}
```

#### 响应参数

**`data` 字段结构：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.video_hash` | `string` | 视频内容哈希 |
| `data.descriptions` | `SceneDescriptionItem[]` | 场景描述列表，按 `scene_index` 排序 |
| `data.descriptions[].scene_index` | `int` | 场景序号（从 0 开始） |
| `data.descriptions[].grid_image` | `string` | 对应的缩略图文件名 |
| `data.descriptions[].description` | `string` | 大模型生成的场景描述文本。`status != "ok"` 时为空字符串 |
| `data.descriptions[].status` | `string` | 描述状态：`ok` / `skipped` / `failed` |
| `data.descriptions[].error` | `string \| null` | 失败时的错误信息 |
| `data.warnings` | `WarningDTO[]` | 警告信息列表（每个失败场景对应一条） |

#### 响应示例

**部分成功：**

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "video_hash": "a1b2c3d4e5f67890",
    "descriptions": [
      {
        "scene_index": 0,
        "grid_image": "scene_001.jpg",
        "description": "阳光明媚的户外公园，绿色草坪上有几个孩子在奔跑玩耍，远处可见树木和蓝天白云",
        "status": "ok",
        "error": null
      },
      {
        "scene_index": 1,
        "grid_image": "scene_002.jpg",
        "description": "室内客厅场景，三人坐在灰色沙发上交谈，墙上挂着一幅风景画",
        "status": "ok",
        "error": null
      },
      {
        "scene_index": 2,
        "grid_image": "scene_003.jpg",
        "description": "",
        "status": "failed",
        "error": "Connection timeout"
      }
    ],
    "warnings": [
      {
        "code": "DESC_LLM_ERROR",
        "message": "场景 2 描述失败: Connection timeout",
        "scope": "scene_description",
        "target_id": "2"
      }
    ]
  }
}
```

---

### 5.4 清除缓存 — DELETE /api/v1/video/cache

```
DELETE /api/v1/video/cache
Content-Type: application/json
```

#### 功能说明

根据视频路径（计算内容哈希后）删除对应的缓存目录，包括结构化结果元数据和缩略图。视频文件本身不受影响。

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `video_path` | `string` | **必填** | 视频文件路径，相对于 `data_base_path` |

#### 请求示例

```http
DELETE /api/v1/video/cache HTTP/1.1
Content-Type: application/json

{
  "video_path": "video/sample.mp4"
}
```

#### 响应示例

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": null
}
```

---

### 5.5 存储路径 — GET /api/v1/video/storage

```
GET /api/v1/video/storage
```

#### 功能说明

查询结构化服务的数据根目录和场景缓存目录的绝对路径。用于外部服务（如 Immich ML Server）定位网格图文件。

#### 请求参数

无

#### 响应参数

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.data_base_path` | `string` | 视频数据基础路径（绝对路径） |
| `data.cache_base_path` | `string` | 结构化输出缓存根目录（绝对路径） |
| `data.scenes_path` | `string` | 场景缓存根目录（绝对路径，=`cache_base_path/scenes`） |

#### 响应示例

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "data_base_path": "/data",
    "cache_base_path": "/data/video-structure-cache",
    "scenes_path": "/data/video-structure-cache/scenes"
  }
}
```

---

### 5.6 异步任务 API — /api/v2/*/jobs

异步任务接口用于提交长耗时的视频处理任务，并通过轮询查询任务状态。任务存储在共享 jobs 表中，相同 `job_type + video_hash` 若已有 `queued` 或 `running` 任务，会直接复用现有 `job_id`。

#### 通用任务状态

| 状态 | 说明 |
|---|---|
| `queued` | 已入队，等待 worker 执行 |
| `running` | worker 正在执行 |
| `succeeded` | 执行成功，`result` 非空 |
| `failed` | 执行失败，`error` 非空 |

#### 通用提交响应

所有 `POST .../jobs` 成功时返回 `ResponseDTO<JobSubmitResponse>`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.job_id` | `string` | 任务 ID，UUID 字符串 |
| `data.status` | `string` | 固定为 `queued` |
| `data.poll_url` | `string` | 查询任务状态的相对路径 |

示例：

```json
{
  "code": 0,
  "msg": "操作成功",
  "data": {
    "job_id": "8c30a7f2-8263-471d-9c7b-4fc00d9f38dd",
    "status": "queued",
    "poll_url": "/api/v2/scenes/detect/jobs/8c30a7f2-8263-471d-9c7b-4fc00d9f38dd"
  }
}
```

#### 通用查询响应

所有 `GET .../jobs/{job_id}` 成功时返回 `ResponseDTO<JobStatusResponse>`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.job_id` | `string` | 任务 ID |
| `data.type` | `string` | 任务类型：`scene_detect` / `structure` / `describe` |
| `data.status` | `string` | 任务状态：`queued` / `running` / `succeeded` / `failed` |
| `data.created_at` | `int \| null` | 创建时间 Unix 秒时间戳 |
| `data.started_at` | `int \| null` | 开始执行时间 Unix 秒时间戳 |
| `data.finished_at` | `int \| null` | 完成时间 Unix 秒时间戳 |
| `data.attempt` | `int` | 执行尝试次数 |
| `data.result` | `object \| null` | 成功结果。仅 `status="succeeded"` 时非空，结构取决于任务类型 |
| `data.error` | `JobErrorDTO \| null` | 失败信息。仅 `status="failed"` 时非空 |
| `data.error.code` | `string \| null` | 任务错误代码 |
| `data.error.message` | `string \| null` | 错误消息 |
| `data.error.detail` | `string \| null` | 错误详情 |

#### 场景检测异步任务

```
POST /api/v2/scenes/detect/jobs
GET  /api/v2/scenes/detect/jobs/{job_id}
```

提交请求字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `video_path` | `string` | **必填** | — | 视频文件路径。相对于 scene-detect 的 `data_base_path`，也支持绝对路径 |
| `threshold` | `float \| null` | 可选 | `null` | 场景检测阈值。`null` 时按视频时长策略自动选择 |
| `max_scenes` | `int \| null` | 可选 | `null` | 最大场景数。`null` 时按视频时长策略自动选择，`0` 表示不限制 |
| `scale_width` | `int \| null` | 可选 | `null` | 检测管道 scale 宽度。`null` 使用服务端配置，`0` 表示不缩放 |
| `decode_threads` | `int \| null` | 可选 | `null` | ffmpeg 解码线程数。`null` 使用服务端配置，`0` 表示 ffmpeg auto |
| `cache_enabled` | `bool` | 可选 | `true` | 是否复用相同视频未完成的 scene-detect job。`false` 时每次提交都会创建新任务 |

提交示例：

```json
{
  "video_path": "video/sample.mp4",
  "threshold": 30.0,
  "max_scenes": 80,
  "scale_width": 640,
  "decode_threads": 2,
  "cache_enabled": true
}
```

成功结果 `data.result` 结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `metadata` | `SceneMetadata` | 视频元信息 |
| `policy` | `ScenePolicyDTO` | 本次检测实际生效的策略参数 |
| `scenes` | `SceneBoundary[]` | 场景边界列表 |
| `warnings` | `WarningDTO[]` | 警告信息 |

#### 视频结构化异步任务

```
POST /api/v2/video/structure/jobs
GET  /api/v2/video/structure/jobs/{job_id}
```

提交请求字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `video_path` | `string` | **必填** | — | 视频文件路径。相对于 structure 的 `data_base_path`，也支持绝对路径 |
| `scenes` | `SceneBoundaryInput[] \| null` | 条件必填 | `null` | 场景边界列表。与 `detect_job_id` 二选一 |
| `detect_job_id` | `string \| null` | 条件必填 | `null` | 已成功的 scene-detect job ID。与 `scenes` 二选一 |
| `frame_grid` | `bool` | 可选 | `true` | 是否生成场景拼图 |
| `force` | `bool` | 可选 | `false` | 强制重新结构化，忽略已有缓存 |
| `cache_enabled` | `bool` | 可选 | `true` | 是否启用结构化缓存读写和相同视频未完成任务复用。`false` 时 worker 不读写缓存，每次提交都会创建新任务 |
| `grid_rows` | `int` | 可选 | `3` | 场景图片拼接行数。注意异步接口默认是 3 |
| `grid_cols` | `int` | 可选 | `3` | 场景图片拼接列数。注意异步接口默认是 3 |

`scenes` 与 `detect_job_id` 至少提供一个；如果提供 `detect_job_id`，该 detect job 必须已 `succeeded`，结构化 worker 会读取其 `result.scenes`。

提交示例（引用检测任务）：

```json
{
  "video_path": "video/sample.mp4",
  "detect_job_id": "8c30a7f2-8263-471d-9c7b-4fc00d9f38dd",
  "frame_grid": true,
  "force": false,
  "cache_enabled": true,
  "grid_rows": 3,
  "grid_cols": 3
}
```

提交示例（直接传 scenes）：

```json
{
  "video_path": "video/sample.mp4",
  "scenes": [
    {
      "scene_index": 0,
      "start_frame": 0,
      "end_frame": 450,
      "start_time": 0.0,
      "end_time": 15.02
    }
  ],
  "cache_enabled": false,
  "grid_rows": 1,
  "grid_cols": 1
}
```

成功结果 `data.result` 为 `StructureResultDTO` 完整结构，字段同 [5.2 视频结构化](#52-视频结构化--post-apiv1videostructure)。

#### 场景描述异步任务

```
POST /api/v2/video/describe/jobs
GET  /api/v2/video/describe/jobs/{job_id}
```

提交请求字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `video_hash` | `string` | **必填** | — | 视频内容哈希，由结构化接口或 structure job 返回 |
| `force` | `bool` | 可选 | `false` | 强制重新描述，忽略已有描述缓存 |
| `model_cfg` | `object \| null` | 运行时必填 | `null` | 大模型配置。不传或为 `null` 会在任务执行时失败 |
| `model_cfg.base_url` | `string` | **必填** | — | LLM API 地址（OpenAI 兼容接口） |
| `model_cfg.api_key` | `string` | 可选 | `""` | API Key |
| `model_cfg.model_name` | `string` | **必填** | — | 模型名称 |
| `model_cfg.max_concurrency` | `int` | 可选 | `5` | 并发调用 LLM 的最大场景数 |
| `model_cfg.request_timeout` | `int` | 可选 | `120` | 单次 LLM 请求超时秒数 |

提交示例：

```json
{
  "video_hash": "a1b2c3d4e5f67890",
  "force": false,
  "model_cfg": {
    "base_url": "http://10.144.144.232:21436/v1",
    "api_key": "sk-fake",
    "model_name": "minicpm-v:latest",
    "max_concurrency": 10,
    "request_timeout": 120
  }
}
```

成功结果 `data.result` 为 `SceneDescriptionResult` 完整结构，字段同 [5.3 场景描述](#53-场景描述--post-apiv1videodescribe)。

---

## 6. 典型调用流程

### 完整流水线（场景检测 → 结构化 → 描述）

```
调用方                          Scene-Detect (:8910)       Structure (:8911)
  │                                    │                        │
  │  1. 场景检测                        │                        │
  ├───────────────────────────────────>│                        │
  │  POST /api/v1/scenes/detect        │                        │
  │  { video_path, threshold }         │                        │
  │<───────────────────────────────────┤                        │
  │  { scenes: [{...}, ...] }          │                        │
  │                                    │                        │
  │  2. 视频结构化                       │                        │
  ├────────────────────────────────────────────────────────────>│
  │  POST /api/v1/video/structure                                │
  │  { video_path, scenes, grid_rows, grid_cols }               │
  │<────────────────────────────────────────────────────────────┤
  │  { video_hash, scenes[].grid_image, ... }                   │
  │                                    │                        │
  │  3. 场景描述（可选）                  │                        │
  ├────────────────────────────────────────────────────────────>│
  │  POST /api/v1/video/describe                                 │
  │  { video_hash, model_cfg }                                  │
  │<────────────────────────────────────────────────────────────┤
  │  { descriptions: [{ description, status }, ...] }           │
```

### 缓存机制说明

- **步骤 1（场景检测）不缓存** — 同步请求每次都重新检测；异步任务默认只复用相同视频尚未完成的任务，传 `cache_enabled=false` 可关闭复用
- **步骤 2（结构化）有缓存** — 基于视频内容哈希（MD5 快速采样），同一视频的不同路径请求会命中缓存。传 `force=true` 可跳过读取已有缓存并重写缓存；传 `cache_enabled=false` 会完全关闭本次请求的缓存读写和异步任务复用
- **步骤 3（描述）有独立缓存** — 描述结果存储在 `_descriptions.json` 中，传 `force=true` 可强制重新生成
- **场景缩略图文件持久化** — 保存在 `scenes/{video_hash}/grids/scene_NNN.jpg`，与元数据缓存独立

### 缓存目录结构

```
{scenes_path}/{video_hash}/
├── _cached.json            # 结构化结果元数据
├── _descriptions.json      # 场景描述缓存
└── grids/
    ├── scene_001.jpg       # 第 1 个场景缩略图
    ├── scene_002.jpg       # 第 2 个场景缩略图
    └── ...
```

---

*基于 video-instruction v0.1.0 源码分析生成 · 2026-07-29*
