# video-instruction Makefile
# Dev:  docker/docker-compose.dev.yml（源码 volume 挂载 + debugpy + --reload）
# Prod: docker/docker-compose.yml
#
# 用法:
#   make dev          启动 dev 服务
#   make build        构建 prod 镜像（自动带平台标签）
#   make tag          将构建版本另标为 latest-$(PLATFORM)
#   make push         推送版本标签 + latest-$(PLATFORM) 到 registry
#
# 版本:
#   IMAGE_TAG 环境变量覆盖镜像标签（默认 latest）
#   BUILD_TAG 自动追加平台前缀：amd64_20260629_abc1234 / arm64_20260629_abc1234
#   不同平台构建互不覆盖，可共存于 registry

REGISTRY ?= swr.cn-southwest-2.myhuaweicloud.com/ictrek
IMAGE_NAME ?= video-instruction
OPTS  ?=  # 传给 docker/compose 的额外参数（如 -d、--no-cache）

DEV_COMPOSE  := docker/docker-compose.dev.yml
DEV_ENV_FILE := docker/.env.dev
DEV_CMD      := docker compose --env-file $(DEV_ENV_FILE) -f $(DEV_COMPOSE)

PROD_COMPOSE := docker/docker-compose.yml
PROD_ENV_FILE := docker/.env.prod
PROD_CMD     := docker compose --env-file $(PROD_ENV_FILE) -f $(PROD_COMPOSE)

GIT_HASH   := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_DATE := $(shell date +%Y%m%d)
PLATFORM   := $(shell uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
BUILD_TAG  := $(PLATFORM)_$(BUILD_DATE)_$(GIT_HASH)

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

.PHONY: build tag push prod prod-down prod-logs

build:  ## [Prod] 构建镜像 + 更新 latest-$(PLATFORM)
	IMAGE_TAG=$(BUILD_TAG) $(PROD_CMD) build $(OPTS)
	docker tag $(REGISTRY)/$(IMAGE_NAME)-detection:$(BUILD_TAG)  $(REGISTRY)/$(IMAGE_NAME)-detection:latest-$(PLATFORM)
	docker tag $(REGISTRY)/$(IMAGE_NAME)-structure:$(BUILD_TAG)  $(REGISTRY)/$(IMAGE_NAME)-structure:latest-$(PLATFORM)
tag:  ## [Prod] 将构建的版本镜像设为 latest-$(PLATFORM)（多平台互不覆盖）
	docker tag $(REGISTRY)/$(IMAGE_NAME)-detection:$(BUILD_TAG)  $(REGISTRY)/$(IMAGE_NAME)-detection:latest-$(PLATFORM)
	docker tag $(REGISTRY)/$(IMAGE_NAME)-structure:$(BUILD_TAG)  $(REGISTRY)/$(IMAGE_NAME)-structure:latest-$(PLATFORM)
push:  ## [Prod] 推送版本标签 + 平台 latest 到 registry
	docker push $(REGISTRY)/$(IMAGE_NAME)-detection:$(BUILD_TAG)
	docker push $(REGISTRY)/$(IMAGE_NAME)-structure:$(BUILD_TAG)
	docker push $(REGISTRY)/$(IMAGE_NAME)-detection:latest-$(PLATFORM)
	docker push $(REGISTRY)/$(IMAGE_NAME)-structure:latest-$(PLATFORM)
prod:  ## [Prod] 启动服务（加 OPTS=-d 后台运行）
	$(PROD_CMD) up $(OPTS)
prod-down:  ## [Prod] 停止服务
	$(PROD_CMD) down
prod-logs:  ## [Prod] 查看日志
	$(PROD_CMD) logs -f
