# video-structure Makefile
# Dev:  docker/docker-compose.dev.yml（源码 volume 挂载 + debugpy + --reload）
# Prod: docker/docker-compose.yml
#
# 用法:
#   make dev          启动 dev 服务
#   make build        构建 VOS 发布镜像（不推送）
#   make push         构建并推送 VOS 发布镜像
#
# 发布镜像（VOS 应用打包使用）：
#   入口为 docker/build_image.sh（参考 image-studio docker/build_image.sh 的方式），
#   tag 规则 {amd,arm}_${日期}_${githash}，与构建解耦；构建推送后登记飞书发布表，
#   打包（ictrek.app/scripts/package.sh）从飞书读取各组件最新 tag。
#   不要再走 compose build 打发布镜像，否则 tag 与打包脚本拼出的引用不一致。
#   直接调用：./docker/build_image.sh [--no-push] [--no-feishu] [--tag X] [--base-image <swr-image>]
#   一键发布（构建成功后）：./update_version [patch|minor|major]
#     bump VERSION → 推分支/tag → CI 打包上架（.github/workflows/release.yml）

REGISTRY ?= swr.cn-southwest-2.myhuaweicloud.com/ictrek
IMAGE_NAME ?= video-structure
OPTS  ?=  # 传给 docker/compose 的额外参数（如 -d、--no-cache）

DEV_COMPOSE  := docker/docker-compose.dev.yml
DEV_ENV_FILE := docker/.env.dev
DEV_CMD      := docker compose --env-file $(DEV_ENV_FILE) -f $(DEV_COMPOSE)

PROD_COMPOSE := docker/docker-compose.yml
PROD_ENV_FILE := docker/.env.prod
PROD_CMD     := docker compose --env-file $(PROD_ENV_FILE) -f $(PROD_COMPOSE)

# 注：发布镜像的 tag 由 build_image.sh 从 ictrek.app/VERSION 推导，Makefile 不再维护 BUILD_TAG

.DEFAULT_GOAL := help
help:  ## 显示帮助
	@grep -Eh '^[a-zA-Z_.-]+:.*## ' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-28s\033[0m %s\n", $$1, $$2}'

# ── Dev ──

.PHONY: dev dev-down dev-logs dev-build dev-ps

dev:       ## [Dev] 启动服务（加 OPTS=-d 后台运行）
	$(DEV_CMD) --profile detection --profile structure up $(OPTS)
dev-down:  ## [Dev] 停止服务
	$(DEV_CMD) --profile detection --profile structure down
dev-logs:  ## [Dev] 查看日志
	$(DEV_CMD) --profile detection --profile structure logs -f
dev-build: ## [Dev] 构建镜像
	$(DEV_CMD) build scene-detection structure $(OPTS)
dev-ps:    ## [Dev] 查看服务状态
	$(DEV_CMD) --profile detection --profile structure ps

# ── Prod ──

.PHONY: build push prod prod-down prod-logs

build:  ## [Prod] 构建 VOS 发布镜像（tag={amd,arm}_<日期>_<githash>，不推送）
	./docker/build_image.sh --no-push

push:  ## [Prod] 构建并推送 VOS 发布镜像到 registry
	./docker/build_image.sh
prod:  ## [Prod] 启动服务（加 OPTS=-d 后台运行）
	$(PROD_CMD) up $(OPTS)
prod-down:  ## [Prod] 停止服务
	$(PROD_CMD) down
prod-logs:  ## [Prod] 查看日志
	$(PROD_CMD) logs -f
