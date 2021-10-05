#!/bin/bash

DOCKER_CONF="${PWD}/.docker"

IMAGE_NAME="quay.io/cloudservices/houndigrade"
GIT_TAG=$(git describe --tags $(git rev-list --tags --max-count=1))

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi

if [[ -z "$RH_REGISTRY_USER" || -z "$RH_REGISTRY_TOKEN" ]]; then
    echo "RH_REGISTRY_USER and RH_REGISTRY_TOKEN  must be set"
    exit 1
fi

mkdir -p "${DOCKER_CONF}"

# Log into the registries
docker --config="${DOCKER_CONF}" login -u="${QUAY_USER}" -p="${QUAY_TOKEN}" quay.io
docker --config="${DOCKER_CONF}" login -u="$RH_REGISTRY_USER" -p="$RH_REGISTRY_TOKEN" registry.redhat.io

# Check if semver tagged image already exists, or this is the first build of it.
if [[ ! "docker --config="${DOCKER_CONF}" pull ${IMAGE_NAME}:${GIT_TAG}" ]]; then
    echo "First time encountering ${GIT_TAG}, building..."
    push_git_tag=true
else
    echo "${GIT_TAG} already exists, skipping building tag."
fi

# Pull 'Latest' Image
docker --config="${DOCKER_CONF}" pull ${IMAGE_NAME}:latest || true

# Build and Tag
docker --config="${DOCKER_CONF}" build --cache-from ${IMAGE_NAME}:latest --tag "${IMAGE_NAME}:latest" .
if [[ "$push_git_tag" = true ]]; then
    docker --config="${DOCKER_CONF}" tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:${GIT_TAG}"
fi

# Push images
docker --config="${DOCKER_CONF}" push "${IMAGE_NAME}:latest"
if [[ "$push_git_tag" = true ]]; then
    docker --config="${DOCKER_CONF}" push "${IMAGE_NAME}:${GIT_TAG}"
fi
