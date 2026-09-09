# 视频理解（Video Instruction）

视频场景检测（scene-detect）与视频结构化（structure）双服务应用，供 VOS 平台内其他应用接入。

## 能力

- **scene-detect（默认宿主端口 48910）**：ffprobe 元数据 → PySceneDetect 场景边界检测，返回 `scenes[]`
- **structure（默认宿主端口 48911）**：按场景抽帧生成九宫格 → staging 暂存 → tar 产物 Pull 交付；可选 VLM 场景描述（describe）
- **接入文档页面**：导航「视频结构化 → 接入文档」，同域 iframe 打开完整 HTTP API 说明

## 接入要点

1. **Base URL（VOS 内直连，推荐）**：`http://<host>:48910` / `http://<host>:48911`
2. **网关 URL**：`http://${VOS_HOST_GW_IP}:${VOS_API_GW_PORT_INTERNAL}/api/com.ictrek.video-structure/{scene|structure}`
3. **video_path 请传 `http(s)://` URL**：把视频暴露成服务端容器可访问的 URL（同机经 `172.17.0.1`），不要写 `localhost`；本地路径模式要求三方挂载点一致，不推荐。
4. 异步 Job：提交 → 轮询 `GET .../jobs/{id}` 到 `succeeded` → 下载 artifact → `DELETE` 释放 staging。
5. 业务错误也返回 HTTP 200，**只看响应体 `code` 判成败**。

完整接口契约见应用内「接入文档」页面。

## 部署形态

一个应用两个容器（scene-detection + structure），共享 `data/` 卷（jobs/队列 SQLite）与 `staging/` 卷（产物暂存），**必须调度到同一宿主**。

## 配置项

安装时通过 `configs.yml` 收集，仅保留必要项：两个服务宿主端口（默认 48910/48911）与 describe 默认 LLM 配置（地址 / Key / 模型名）。其余参数使用服务端内置默认值。
