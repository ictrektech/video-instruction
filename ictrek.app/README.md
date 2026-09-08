# video-structure VOS 应用打包说明

本目录包含 VOS app `com.ictrek.video-structure` 的安装包模板，结构与 vai monorepo 的
`apps/<app>/ictrek.app/` 一致（video-structure 是单应用仓库，故直接放在仓库根）。

## 目录

```text
ictrek.app/
├── VERSION                  # 应用版本（打包占位 __APP_VERSION__ 的来源）
├── src/
│   ├── manifest.yml         # 应用元数据 / profiles / frontend / storage
│   ├── docker-compose.yml   # 双容器编排 + Traefik labels（amd / arm 两个 profile）
│   ├── configs.yml          # 安装期配置项（仅必要项）
│   ├── routers.yml          # 导航注册：视频结构化 → 接入文档（iframe）
│   ├── README.zh-CN.md      # 应用商店说明（默认语言）
│   └── README.en.md
├── scripts/
│   ├── package.sh           # 本地打包（pull 模式，从飞书读各组件最新镜像 tag）
│   ├── update_version.sh    # 发布决策：bump VERSION + commit + 推分支/tag
│   └── feishu.sh            # 飞书发布表读写共享库（build/package 共用）
└── dist/                    # 打包产物（本地生成）
```

根目录另有 `docker/build_image.sh`（构建推送镜像 + 登记飞书）与 `./update_version`
一键发布入口（bump 版本 + 推 tag）。

## 打包模式：pull

包内**不内嵌镜像归档**，只含 `docker-compose.yml` 与元数据；两个镜像引用（amd / arm）写入包内
`.env`，平台安装时从 registry 拉取。包内 `docker-compose.yml` 含 `amd`、`arm` 两个 profile，
安装时由 VOS 指定其中一个。

**单镜像**：场景检测与结构化两个容器共用同一镜像（依赖相同），仅靠 `command`
（`scene-detect` / `structure`）与 `APP_PORT`（8910 / 8911）区分角色。

镜像 tag 与发布解耦：**构建 tag 是 `<平台>_<日期>_<githash>`**（如 `amd_20260908_1a2b3c4`），
每次构建唯一、一天多次构建互不覆盖。构建推送后由 `build_image.sh` 登记到飞书发布表
（单一组件列 `video-structure`，映射 sheet：amd → `AMD_with_mxn100`、
arm → `ARM_without_cuda`）；打包时读取该组件列最新 tag：

```text
swr.cn-southwest-2.myhuaweicloud.com/ictrek/video-structure:{amd,arm}_<最新tag>
# 本地调试（跳过飞书，按约定拼装）
IMAGE_TAG=20260908_1a2b3c4 ./ictrek.app/scripts/package.sh
# 或覆盖
VIDEO_STRUCTURE_AMD_IMAGE=...:amd_20260908_1a2b3c4 ./ictrek.app/scripts/package.sh
```

## 发布流程

**先构建（成功后自动登记飞书）→ 再做版本决策 → CI 打包上架**。
构建失败不污染版本历史；远程推送时机后移，不会出现"远程已有版本但镜像不存在"的中间态。

```bash
# ① 各架构构建机上原生构建并推送镜像 + 登记飞书（docker/build_image.sh，自动识别 amd/arm）
#    两台构建机必须基于同一 commit；跨天构建用 --tag 对齐
ssh tc232 'cd video-structure && git pull && ./docker/build_image.sh'   # amd_20260908_1a2b3c4
ssh tc192 'cd video-structure && git pull && ./docker/build_image.sh'   # arm_20260908_1a2b3c4
#    只构建不推送：./docker/build_image.sh --no-push（不登记飞书）
#    基镜像建议先镜像到 SWR（参考 image-studio docker/mirror_base_images.sh）：
#    ./docker/build_image.sh --base-image swr.cn-southwest-2.myhuaweicloud.com/ictrek/python:amd_3.13-slim

# ② 一键发布（根目录 ./update_version）：bump VERSION + commit + 推分支 + 推 release tag
./update_version patch

# ③ CI 自动发布：tag 触发 .github/workflows/release.yml，
#    从飞书读取最新镜像 tag 打包（含 YAML 校验）→ 挂 GitHub Release
#    → 配置了 APPSTORE_IP/APPSTORE_TOKEN 时自动上架 VOS App Store
```

前置条件：

- 构建机/发布机需要飞书应用凭据：`~/.feishu.json`（或 `~/.feishu.components.json`），
  内容 `{"feishu_app_id": "...", "feishu_app_secret": "..."}`；
- GitHub 仓库 Secrets（供 release.yml 使用，与 image-studio 同名可复用）：
  - `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书应用凭据（必须）
  - `FEISHU_SPREADSHEET_TOKEN`：发布表 token（可选，缺省用脚本内置值）
  - `APPSTORE_IP` / `APPSTORE_TOKEN`：VOS App Store 自动上架（可选，未配置则跳过上架）；
    APPSTORE_TOKEN 是 App Store SSH 通道（端口 32222，tunneluser）的密码
- 首次登记时组件列会自动创建（无需手工建列）。

本地调试打包（不修改 VERSION、不读飞书）：

```bash
PACKAGE_VERSION=0.1.0 IMAGE_TAG=20260908_1a2b3c4 ./ictrek.app/scripts/package.sh
# 产出 ictrek.app/dist/video-structure_0.1.0_pull.tar
```

手动校验 compose（只启用一个 profile）：

```bash
docker compose --profile amd config
docker compose --profile arm config
```

## 部署约束（务必确认）

1. **两容器必须同一宿主**：共享 `data/` 卷（jobs 表 + Huey 队列是同一个 SQLite `huey.db`），
   跨宿主会同时导致 `detect_job_id` 引用失效、队列状态分裂。
2. **`data/` 必须在本地磁盘，不能在 NFS/NAS**：Huey 默认启用 SQLite WAL
   （`journal_mode=wal` + `busy_timeout=5000ms`），WAL 依赖 `-shm` 共享内存文件，
   在 NFS 上会出现锁失败或数据损坏。若 `VOS_APP_STORAGE_PATH` 指向 NAS，
   需要给 `SqliteHuey` 传入 `journal_mode` 覆盖（改代码），或改用本地盘路径。
3. **`staging/` 两容器都可写**：worker 对等注册两类任务，任一容器都可能写产物。
4. **日志按容器分目录**（`logs/video-structure-detect`、`logs/video-structure`）：
   两容器各有 API + worker 两个进程，共用同一个 `server.log` 会因
   `RotatingFileHandler` 非多进程安全导致轮转竞态、日志损坏。
5. **Worker 并发由 command 的 `--workers` 决定**：`HUEY_WORKERS` 环境变量当前无效
   （`run_worker` 只解析 CLI 参数），改并发请改 compose 的 command。
