#!/bin/bash
# OpenAudio S1-mini용 fish-speech 서버 이미지 빌드 (ADR-0005)
#
# 왜 빌드하나: 사전빌드 fishaudio/fish-speech 태그 중 s1-mini 호환 이미지가 없다.
#   - server-cuda(rolling): S2용. FishTokenizer가 HF AutoTokenizer라 s1-mini의
#     tiktoken(model_type=dual_ar)을 못 읽어 warm-up에서 크래시.
#   - v1.5.1: firefly decoder/8 codebook. modded_dac/10 codebook(s1-mini) 미지원.
#   - OpenAudio S1은 별도 버전 태그 없이 main 브랜치로만 릴리스됨.
# 따라서 tiktoken + modded_dac을 둘 다 가진 S1 커밋에서 직접 빌드한다.
set -e

# S2 beta 직전 S1 tip 커밋 (tiktoken + modded_dac, 기본 체크포인트=openaudio-s1-mini)
FS_COMMIT="${FS_COMMIT:-d3df50503b36314a964f66cac1af1e19e95bcfa3}"
IMAGE_TAG="${IMAGE_TAG:-wagglebot/fish-speech-s1:cuda}"
BUILD_DIR="$(mktemp -d)"

echo "========================================"
echo "  fish-speech S1 서버 이미지 빌드"
echo "========================================"
echo "커밋: $FS_COMMIT"
echo "태그: $IMAGE_TAG"
echo ""

echo "[1/3] S1 소스 다운로드..."
curl -sL "https://github.com/fishaudio/fish-speech/archive/${FS_COMMIT}.tar.gz" \
    -o "$BUILD_DIR/src.tar.gz"
tar xzf "$BUILD_DIR/src.tar.gz" -C "$BUILD_DIR"
SRC_DIR="$(find "$BUILD_DIR" -maxdepth 1 -type d -name 'fish-speech-*' | head -1)"
echo "      추출: $SRC_DIR"

echo "[2/3] server/cuda 이미지 빌드 (~10~20분, torch+CUDA 설치)..."
DOCKER_BUILDKIT=1 docker build \
    -f "$SRC_DIR/docker/Dockerfile" \
    --build-arg BACKEND=cuda \
    --target server \
    -t "$IMAGE_TAG" \
    "$SRC_DIR"

echo "[3/3] 정리..."
rm -rf "$BUILD_DIR"

echo ""
echo "========================================"
echo "  완료: $IMAGE_TAG"
echo "========================================"
echo "  docker compose -f env/docker-compose.yml up -d --no-deps fish-speech"
echo "  docker compose -f env/docker-compose.yml logs -f fish-speech   # 'Models warmed up' 확인"
