#!/bin/bash

set -exv

GIT_TAG=$(git tag --contains | head -1)
GIT_TAG=${GIT_TAG:-latest}

IMAGE_TAG=$(git rev-parse HEAD)
SHORT_IMAGE_TAG=$(git rev-parse --short=7 HEAD)

GITHUB_IMAGE_NAME=ghcr.io/cloudigrade/houndigrade
IMAGE_NAME=quay.io/cloudservices/houndigrade

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi

DOCKER_CONF="$PWD/.docker"
mkdir -p "$DOCKER_CONF"
docker --config="$DOCKER_CONF" login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
docker --config="$DOCKER_CONF" pull "${GITHUB_IMAGE_NAME}:${IMAGE_TAG}"
docker --config="$DOCKER_CONF" tag "${GITHUB_IMAGE_NAME}:${IMAGE_TAG}" "${IMAGE_NAME}:${GIT_TAG}"
docker --config="$DOCKER_CONF" tag "${GITHUB_IMAGE_NAME}:${IMAGE_TAG}" "${IMAGE_NAME}:${SHORT_IMAGE_TAG}"
docker --config="$DOCKER_CONF" push "${IMAGE_NAME}:${GIT_TAG}"
docker --config="$DOCKER_CONF" push "${IMAGE_NAME}:${SHORT_IMAGE_TAG}"
