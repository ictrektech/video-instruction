#!/usr/bin/env bash
# video-structure VOS 应用打包（pull 模式）
#
# pull 模式：包内只有 docker-compose.yml + manifest/configs/routers/README，
# 不内嵌镜像归档；镜像名写入包内 .env，平台安装时从 registry 拉取。
#
# 用法：
#   ./ictrek.app/scripts/package.sh                       # 版本取 ictrek.app/VERSION
#   PACKAGE_VERSION=0.1.1 ./ictrek.app/scripts/package.sh # 手动指定版本（本地调试）
#
# 单镜像：scene-detect 与 structure 共用同一镜像（仅 command 不同）。
# 镜像 tag 从飞书发布表读取组件 video-structure 的最新 tag（build_image.sh 登记）；
# 本地调试可跳过飞书：
#   IMAGE_TAG=20260908_1a2b3c4 ./ictrek.app/scripts/package.sh
# 或覆盖镜像引用：
#   VIDEO_STRUCTURE_AMD_IMAGE=... VIDEO_STRUCTURE_ARM_IMAGE=... ./ictrek.app/scripts/package.sh
#
# 产物：ictrek.app/dist/video-structure_${VERSION}_pull.tar（内含 app.tar.gz）

set -euo pipefail

APP_NAME="video-structure"
IMAGE_REPO="${VIDEO_STRUCTURE_IMAGE_REPO:-swr.cn-southwest-2.myhuaweicloud.com/ictrek}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/src"
DIST_DIR="${ROOT_DIR}/dist"
STAGE_DIR="${DIST_DIR}/staging"
PACKAGE_ROOT="${DIST_DIR}/package-root"
VERSION_FILE="${ROOT_DIR}/VERSION"
APP_VERSION="${PACKAGE_VERSION:-$(tr -d '[:space:]' < "${VERSION_FILE}")}"

[[ "${APP_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "invalid version: ${APP_VERSION}" >&2; exit 1; }
command -v tar >/dev/null || { echo "missing tar" >&2; exit 1; }

log() { echo "[package] $*"; }

# 镜像解析优先级：环境变量覆盖 > IMAGE_TAG（本地调试，跳过飞书） > 飞书组件最新 tag
# profile → sheet 的映射与 build_image.sh 的登记保持一致（CPU-only 应用）
resolve_image() { # <amd|arm> -> 输出该架构的镜像引用
  local arch="$1" sheet
  case "$arch" in
    amd) sheet="AMD_with_mxn100" ;;
    arm) sheet="ARM_without_cuda" ;;
    *) echo "unknown profile: $arch" >&2; return 1 ;;
  esac
  feishu_resolve_image "$sheet" "video-structure" "${IMAGE_REPO}/video-structure"
}

if [[ -n "${IMAGE_TAG:-}" ]]; then
  log "IMAGE_TAG=${IMAGE_TAG}：跳过飞书，按约定拼装镜像引用"
  AMD_IMAGE="${VIDEO_STRUCTURE_AMD_IMAGE:-${IMAGE_REPO}/video-structure:amd_${IMAGE_TAG}}"
  ARM_IMAGE="${VIDEO_STRUCTURE_ARM_IMAGE:-${IMAGE_REPO}/video-structure:arm_${IMAGE_TAG}}"
else
  # shellcheck source=feishu.sh
  source "${ROOT_DIR}/scripts/feishu.sh"
  command -v curl >/dev/null || { echo "missing curl（读取飞书需要）" >&2; exit 1; }
  feishu_load_auth
  AMD_IMAGE="$(resolve_image amd)"
  ARM_IMAGE="$(resolve_image arm)"
fi

AMD_IMAGE="${VIDEO_STRUCTURE_AMD_IMAGE:-${AMD_IMAGE}}"
ARM_IMAGE="${VIDEO_STRUCTURE_ARM_IMAGE:-${ARM_IMAGE}}"

rm -rf "${STAGE_DIR}" "${PACKAGE_ROOT}"
mkdir -p "${STAGE_DIR}" "${PACKAGE_ROOT}"
trap 'rm -rf "${STAGE_DIR}" "${PACKAGE_ROOT}"' EXIT

# 镜像引用写入包内 .env（平台 docker compose --env-file 注入）
cat > "${STAGE_DIR}/.env" <<EOF
VIDEO_STRUCTURE_AMD_IMAGE=${AMD_IMAGE}
VIDEO_STRUCTURE_ARM_IMAGE=${ARM_IMAGE}
EOF
log "amd image: ${AMD_IMAGE}"
log "arm image: ${ARM_IMAGE}"

# 渲染 __APP_VERSION__ 并校验产物
python3 - "${SRC_DIR}" "${STAGE_DIR}" "${APP_VERSION}" \
  "${AMD_IMAGE}" "${ARM_IMAGE}" <<'PY'
import re
import sys
from pathlib import Path

src, dst = map(Path, sys.argv[1:3])
APP_VERSION = sys.argv[3]
expected_images = sys.argv[4:6]

for name in (
    "manifest.yml",
    "configs.yml",
    "routers.yml",
    "docker-compose.yml",
    "README.zh-CN.md",
    "README.en.md",
):
    text = (src / name).read_text(encoding="utf-8").replace("__APP_VERSION__", APP_VERSION)
    (dst / name).write_text(text, encoding="utf-8")

# 把 .env 中的镜像引用渲染进 compose（平台不再做插值，包内必须是确定的镜像 tag）
env = dict(
    line.split("=", 1)
    for line in (dst / ".env").read_text(encoding="utf-8").splitlines()
    if "=" in line
)
compose = (dst / "docker-compose.yml").read_text(encoding="utf-8")
for key, value in env.items():
    compose = compose.replace("${" + key + "}", value)
(dst / "docker-compose.yml").write_text(compose, encoding="utf-8")

for key in (
    "VIDEO_STRUCTURE_AMD_IMAGE",
    "VIDEO_STRUCTURE_ARM_IMAGE",
):
    if "${" + key + "}" in compose:
        raise SystemExit(f"unrendered image variable: {key}")

try:
    import yaml  # noqa: PLC0415
except ImportError:
    print("[package][WARN] PyYAML not installed, skip YAML schema validation")
else:
    for name in ("manifest.yml", "configs.yml", "routers.yml", "docker-compose.yml"):
        yaml.safe_load((dst / name).read_text(encoding="utf-8"))

text_parts = [(dst / ".env").read_text(encoding="utf-8")]
text_parts += [(dst / n).read_text(encoding="utf-8") for n in ("manifest.yml", "configs.yml", "routers.yml", "docker-compose.yml", "README.zh-CN.md", "README.en.md")]
if re.search(r"__[A-Z0-9_]+__", "\n".join(text_parts)):
    raise SystemExit("unrendered placeholder left in package")

manifest = (dst / "manifest.yml").read_text(encoding="utf-8")
if f"version: {APP_VERSION}" not in manifest:
    raise SystemExit("manifest version not rendered")
for expected in ("profiles:", "frontend:", "storage:"):
    if expected not in manifest:
        raise SystemExit(f"manifest missing {expected}")

routers = (dst / "routers.yml").read_text(encoding="utf-8")
for expected in (
    "com-ictrek-video-structure",
    "iframe-src: /app/com.ictrek.video-structure/doc/integration.html",
    "entry-point: true",
    "embed: true",
):
    if expected not in routers:
        raise SystemExit(f"routers.yml missing {expected}")

env_text = (dst / ".env").read_text(encoding="utf-8")
for image in expected_images:
    if image not in env_text:
        raise SystemExit(f"missing image in .env: {image}")

for expected in ("vos_default", "external: true", "traefik.enable=true"):
    if expected not in compose:
        raise SystemExit(f"docker-compose.yml missing {expected}")
PY

tar czf "${PACKAGE_ROOT}/app.tar.gz" -C "${STAGE_DIR}" \
  .env manifest.yml configs.yml routers.yml docker-compose.yml README.zh-CN.md README.en.md
tar cf "${DIST_DIR}/${APP_NAME}_${APP_VERSION}_pull.tar" -C "${PACKAGE_ROOT}" app.tar.gz
test "$(tar tf "${DIST_DIR}/${APP_NAME}_${APP_VERSION}_pull.tar" | wc -l | tr -d ' ')" = "1"
echo "Built ${DIST_DIR}/${APP_NAME}_${APP_VERSION}_pull.tar"
