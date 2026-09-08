#!/usr/bin/env bash
# video-structure 发布镜像构建/推送（参考 image-studio docker/build_image.sh 的方式）
#
# 镜像 tag 与构建解耦：<平台>_<日期>_<githash>（如 amd_20260908_1a2b3c4），
# 每次构建唯一、一天多次构建互不覆盖。
#
# 构建推送成功后，将 tag 登记到飞书发布表（单一组件列：video-structure）；
# ictrek.app/scripts/package.sh 打包时读取该组件最新 tag 组装包内 .env
# ——与 image-studio/nowen-video 同一套发布协议。
#
# 发布流程：
#   ① ./docker/build_image.sh            # amd/arm 构建机各一次，同一 commit
# ②  ./update_version [patch|minor|major]   # bump 版本 → CI 打包上架
#
# 镜像全名（单镜像：同时含 scene-detect 与 structure 运行时，靠 command 区分）：
#   swr.cn-southwest-2.myhuaweicloud.com/ictrek/video-structure:{amd,arm}_${TAG}
#
# 基镜像：默认 python:3.13-slim（Docker Hub）。国内构建机建议先镜像到 SWR
# （参考 image-studio docker/mirror_base_images.sh），然后：
#   ./docker/build_image.sh --base-image "${REGISTRY}/python:${arch}_3.13-slim"
# 脚本会以 --pull=false 构建，不触碰 Docker Hub。
#
# 用法：
#   ./docker/build_image.sh                       # 自动识别架构 + 生成 tag，构建并推送
#   ./docker/build_image.sh --no-push             # 只构建，不推送（不登记飞书）
#   ./docker/build_image.sh --no-feishu           # 推送但不登记飞书
#   ./docker/build_image.sh --sheet ARM_without_cuda    # 覆盖登记的飞书 sheet（可多次）
#   ./docker/build_image.sh --tag amd_20260908_1a2b3c4  # 覆盖 tag（amd/arm 跨天构建时对齐用）
#   ./docker/build_image.sh --platform linux/arm64      # 覆盖目标平台（默认本机架构）
#   ./docker/build_image.sh --base-image <image>  # 覆盖基础镜像（SWR 预镜像化后使用）
set -euo pipefail

REGISTRY="swr.cn-southwest-2.myhuaweicloud.com/ictrek"
IMAGE_BASE="${REGISTRY}/video-structure"   # 镜像 repository（不含 tag）
COMPONENT="video-structure"                # 飞书发布表组件列名（package.sh 按此读取）
DOCKERFILE="docker/Dockerfile"
DEFAULT_BASE_IMAGE="python:3.13-slim"

cd "$(dirname "$0")/.."

log() { echo "[build] $*"; }
die() { echo "[build][ERROR] $*" >&2; exit 1; }

# ---------------- args ----------------
DO_PUSH=1
DO_FEISHU=1
TAG_OVERRIDE=""
PLATFORM_OVERRIDE=""
BASE_IMAGE=""
SHEETS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-push) DO_PUSH=0; shift ;;
    --no-feishu) DO_FEISHU=0; shift ;;
    --sheet) SHEETS+=("${2:-}"); shift 2 ;;
    --tag) TAG_OVERRIDE="${2:-}"; shift 2 ;;
    --platform) PLATFORM_OVERRIDE="${2:-}"; shift 2 ;;
    --base-image) BASE_IMAGE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,29p' "$0"; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

# ---------------- arch / platform ----------------
case "$(uname -m)" in
  x86_64|amd64) HOST_PLATFORM=linux/amd64 ;;
  aarch64|arm64) HOST_PLATFORM=linux/arm64 ;;
  *) die "unsupported arch: $(uname -m)" ;;
esac
PLATFORM="${PLATFORM_OVERRIDE:-${HOST_PLATFORM}}"
ARCH="${PLATFORM#linux/}"                       # amd64 | arm64
case "$ARCH" in amd64) ARCH_SHORT=amd ;; *) ARCH_SHORT=arm ;; esac

# CPU-only 应用：amd 登记 AMD_with_mxn100，arm 登记 ARM_without_cuda（--sheet 可覆盖）
if [[ ${#SHEETS[@]} -eq 0 ]]; then
  if [[ "$ARCH_SHORT" == "amd" ]]; then
    SHEETS=("AMD_with_mxn100")
  else
    SHEETS=("ARM_without_cuda")
  fi
fi

# ---------------- tag：平台_日期_githash ----------------
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || die "not a git repo")"
DATE="$(date +%Y%m%d)"
TAG="${TAG_OVERRIDE:-${ARCH_SHORT}_${DATE}_${GIT_SHA}}"

command -v docker >/dev/null || die "missing docker"
docker buildx version >/dev/null 2>&1 || die "missing docker buildx (参考 image-studio：构建机需带 buildx)"
[[ -f "${DOCKERFILE}" ]] || die "Dockerfile not found: ${DOCKERFILE}"
if [[ "${DO_PUSH}" == "1" && "${DO_FEISHU}" == "1" ]]; then
  command -v curl >/dev/null || die "missing curl（登记飞书需要）"
  command -v python3 >/dev/null || die "missing python3（登记飞书需要）"
fi

# 基镜像策略：--base-image 传入 SWR 地址时配合 --pull=false（不碰 Docker Hub）；
# 未传时用 Dockerfile 默认值并允许拉取
BUILD_ARGS=(--load --provenance=false --sbom=false --platform "${PLATFORM}" --builder default)
if [[ -n "${BASE_IMAGE}" ]]; then
  BUILD_ARGS+=(--build-arg "PYTHON_BASE_IMAGE=${BASE_IMAGE}" --pull=false)
  log "base image (SWR): ${BASE_IMAGE} (--pull=false)"
else
  log "base image: ${DEFAULT_BASE_IMAGE} (Docker Hub)"
fi

log "TAG=${TAG} PLATFORM=${PLATFORM} PUSH=${DO_PUSH} SHEETS(${DO_FEISHU})=${SHEETS[*]}"

log "building ${IMAGE_BASE}:${TAG}"
docker buildx build \
  "${BUILD_ARGS[@]}" \
  -f "${DOCKERFILE}" \
  -t "${IMAGE_BASE}:${TAG}" \
  .

if [[ "${DO_PUSH}" == "1" ]]; then
  log "pushing ${IMAGE_BASE}:${TAG}"
  docker push "${IMAGE_BASE}:${TAG}"
else
  log "--no-push: skip push (${IMAGE_BASE}:${TAG})"
fi

# ---------------- 登记飞书发布表（读侧：ictrek.app/scripts/package.sh） ----------------
if [[ "${DO_PUSH}" == "1" && "${DO_FEISHU}" == "1" ]]; then
  # shellcheck source=../ictrek.app/scripts/feishu.sh
  source "ictrek.app/scripts/feishu.sh"
  feishu_load_auth
  for sheet in "${SHEETS[@]}"; do
    feishu_record_build "$sheet" "${COMPONENT}" "${IMAGE_BASE}" "${TAG}"
  done
else
  log "跳过飞书登记（--no-push 或 --no-feishu）"
fi

log "done: ${IMAGE_BASE}:${TAG}"
log "下一步：./update_version [patch|minor|major]"
