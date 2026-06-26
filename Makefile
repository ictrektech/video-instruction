# video-instruction Makefile
# Dev:  docker/docker-compose.dev.yml（源码 volume 挂载 + debugpy + --reload）
# Prod: docker/docker-compose.yml
#
# 用法:
#   make dev          启动 dev 服务
#   make build        构建 prod 镜像
#   make tag          打版本标签
#   make push         推送镜像到 registry

REGISTRY ?= swr.cn-southwest-2.myhuaweicloud.com/ictrek
IMAGE_NAME ?= video-instruction
OPTS  ?=  # 传给 docker/compose 的额外参数（如 -d、--no-cache）

DEV_COMPOSE  := docker/docker-compose.dev.yml
DEV_CMD      := docker compose -f $(DEV_COMPOSE)

PROD_COMPOSE := docker/docker-compose.yml
PROD_CMD     := docker compose -f $(PROD_COMPOSE)

GIT_HASH   := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_DATE := $(shell date +%Y%m%d)
BUILD_TAG  := $(BUILD_DATE)_$(GIT_HASH)

.DEFAULT_GOAL := help
help:  ## 显示帮助
	@grep -Eh '^[a-zA-Z_.-]+:.*## ' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-28s\033[0m %s\n", $$1, $$2}'

# ── Dev ──

.PHONY: dev dev-down dev-logs dev-build dev-ps

dev:       ## [Dev] 启动服务（加 OPTS=-d 后台运行）
	$(DEV_CMD) --profile detection --profile structure up $(OPTS)
dev-down:  ## [Dev] 停止服务
	$(DEV_CMD) down
dev-logs:  ## [Dev] 查看日志
	$(DEV_CMD) --profile detection --profile structure logs -f
dev-build: ## [Dev] 构建镜像
	$(DEV_CMD) build scene-detection structure $(OPTS)
dev-ps:    ## [Dev] 查看服务状态
	$(DEV_CMD) --profile detection --profile structure ps

# ── Prod ──

.PHONY: build tag push prod prod-down prod-logs

build:  ## [Prod] 构建镜像（自动打版本标签）
	IMAGE_TAG=$(BUILD_TAG) $(PROD_CMD) build $(OPTS)
tag:  ## [Prod] 将构建的版本镜像设为 latest
	docker tag $(REGISTRY)/$(IMAGE_NAME):$(BUILD_TAG) $(REGISTRY)/$(IMAGE_NAME):latest
push:  ## [Prod] 推送镜像到 registry
	docker push $(REGISTRY)/$(IMAGE_NAME):$(BUILD_TAG)
	docker push $(REGISTRY)/$(IMAGE_NAME):latest
prod:  ## [Prod] 启动服务（加 OPTS=-d 后台运行）
	$(PROD_CMD) up $(OPTS)
prod-down:  ## [Prod] 停止服务
	$(PROD_CMD) down
prod-logs:  ## [Prod] 查看日志
	$(PROD_CMD) logs -f
