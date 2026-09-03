#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPOSITORY="${CIR_DOCKER_REPOSITORY:-desalvo/cybersecurity-incident-registry}"
TAG="${CIR_DOCKER_TAG:-latest}"
PLATFORMS="${CIR_DOCKER_PLATFORMS:-linux/amd64,linux/arm64}"
BUILDER="${CIR_BUILDX_BUILDER:-cir-multiarch}"
IMAGE_OVERRIDE="${CIR_DOCKER_IMAGE:-}"
PULL_BASE="${CIR_DOCKER_PULL_BASE:-1}"
NO_CACHE="${CIR_DOCKER_NO_CACHE:-1}"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--repository NAME] [--tag TAG] [--image IMAGE] [--platforms LIST] [--builder NAME] [--cache] [--no-pull]

Build and push the Cybersecurity Incident Registry Docker image as a multi-arch
manifest. Defaults:
  repository: desalvo/cybersecurity-incident-registry
  tag:        latest
  image:      desalvo/cybersecurity-incident-registry:latest
  platforms:  linux/amd64,linux/arm64
  builder:    cir-multiarch

Repository and tag can be changed independently with --repository/--tag or the
CIR_DOCKER_REPOSITORY/CIR_DOCKER_TAG environment variables. For backward
compatibility, --image or CIR_DOCKER_IMAGE may be used to provide the complete
image reference and take precedence over repository/tag.

Examples:
  $(basename "$0")
  $(basename "$0") --tag 0.9.0-1
  $(basename "$0") --repository myregistry.example/cir --tag 0.9.0-1
  CIR_DOCKER_REPOSITORY=myorg/cir CIR_DOCKER_TAG=stable $(basename "$0")

By default the build also uses --pull and --no-cache so security validation does not accidentally reuse a stale base image or requirements layer. Use --no-pull and/or --cache only for development.

A multi-platform image cannot be loaded into the classic local Docker image
store as one image, so this script publishes the manifest with --push.
Run 'docker login' for the target registry before executing the script.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repository|--name)
      REPOSITORY="${2:?missing value for $1}"
      shift 2
      ;;
    --tag)
      TAG="${2:?missing value for --tag}"
      shift 2
      ;;
    --image)
      IMAGE_OVERRIDE="${2:?missing value for --image}"
      shift 2
      ;;
    --platforms)
      PLATFORMS="${2:?missing value for --platforms}"
      shift 2
      ;;
    --builder)
      BUILDER="${2:?missing value for --builder}"
      shift 2
      ;;
    --cache)
      NO_CACHE=0
      shift
      ;;
    --no-pull)
      PULL_BASE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -n "$IMAGE_OVERRIDE" ]]; then
  IMAGE="$IMAGE_OVERRIDE"
else
  if [[ -z "$REPOSITORY" || -z "$TAG" ]]; then
    echo "ERROR: repository and tag must not be empty." >&2
    exit 2
  fi
  IMAGE="${REPOSITORY}:${TAG}"
fi

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: Docker is not installed or not in PATH." >&2
  exit 1
}

docker info >/dev/null 2>&1 || {
  echo "ERROR: Docker daemon is not reachable." >&2
  exit 1
}

docker buildx version >/dev/null 2>&1 || {
  echo "ERROR: Docker Buildx is required." >&2
  exit 1
}

if docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
  docker buildx use "$BUILDER"
else
  docker buildx create --name "$BUILDER" --driver docker-container --use >/dev/null
fi

docker buildx inspect --bootstrap >/dev/null

echo "Building multi-arch image: $IMAGE"
echo "Platforms: $PLATFORMS"
echo "Builder: $BUILDER"

BUILD_ARGS=(
  --platform "$PLATFORMS"
  --tag "$IMAGE"
  --push
)

if [[ "$PULL_BASE" == "1" ]]; then
  BUILD_ARGS+=(--pull)
fi
if [[ "$NO_CACHE" == "1" ]]; then
  BUILD_ARGS+=(--no-cache)
fi

docker buildx build "${BUILD_ARGS[@]}" "$ROOT_DIR"

echo "Published: $IMAGE"
docker buildx imagetools inspect "$IMAGE"
