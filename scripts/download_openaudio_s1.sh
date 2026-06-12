#!/bin/bash
# OpenAudio S1-mini 모델 다운로드 (WSL2 / Ubuntu 환경용) — ADR-0005
# ⚠ gated 저장소: HuggingFace 로그인 + 라이선스 동의 필요 (1회).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEST="$PROJECT_ROOT/checkpoints/openaudio-s1-mini"
VENV_DIR="$PROJECT_ROOT/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

echo "========================================"
echo "  OpenAudio S1-mini 다운로드 (WSL2)"
echo "========================================"
echo "대상 경로: $DEST"
echo ""

# ── 1. venv 확인 / 생성
if [ ! -f "$VENV_PYTHON" ]; then
    echo "[1/5] venv 생성 중..."
    python3 -m venv "$VENV_DIR"
else
    echo "[1/5] venv 확인 완료: $VENV_DIR"
fi

# ── 2. 디스크 여유 공간 확인 (최소 5GB 권장)
echo "[2/5] 디스크 공간 확인..."
AVAIL_KB=$(df -k "$PROJECT_ROOT" | tail -1 | awk '{print $4}')
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
if [ "$AVAIL_GB" -lt 5 ]; then
    echo "경고: 디스크 여유 ${AVAIL_GB}GB — 5GB 이상 권장 (모델 ~1GB + 여유)"
    read -r -p "계속 진행? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
else
    echo "      여유 공간: ${AVAIL_GB}GB ✓"
fi

# ── 3. huggingface_hub 설치 확인 + 인증 점검
echo "[3/5] huggingface_hub 및 인증 확인..."
"$VENV_PYTHON" -c "import huggingface_hub" 2>/dev/null || \
    "$VENV_PIP" install --quiet "huggingface_hub[cli]"

# 인증 토큰: HF_TOKEN 환경변수 또는 캐시된 로그인
if ! "$VENV_PYTHON" -c "from huggingface_hub import whoami; whoami()" >/dev/null 2>&1; then
    if [ -z "$HF_TOKEN" ]; then
        echo ""
        echo "  ⚠ HuggingFace 인증이 필요합니다 (openaudio-s1-mini는 gated 저장소)."
        echo "    1) https://huggingface.co/fishaudio/openaudio-s1-mini 접속 → 라이선스 동의"
        echo "    2) 다음 중 하나로 인증:"
        echo "       - $VENV_DIR/bin/hf auth login"
        echo "       - 또는  export HF_TOKEN=hf_xxx  후 재실행"
        exit 1
    fi
fi
echo "      인증 OK ✓"

# ── 4. 모델 다운로드
echo "[4/5] 모델 다운로드 시작 (~1GB)..."
echo ""
"$VENV_PYTHON" - "$DEST" << 'PYEOF'
import os, sys
from huggingface_hub import snapshot_download

local_dir = sys.argv[1]
token = os.environ.get("HF_TOKEN")  # None이면 캐시된 로그인 사용
print(f"저장 위치: {local_dir}")
try:
    snapshot_download(
        repo_id="fishaudio/openaudio-s1-mini",
        local_dir=local_dir,
        local_dir_use_symlinks=False,
        token=token,
    )
except Exception as exc:
    msg = str(exc)
    if "401" in msg or "403" in msg or "gated" in msg.lower():
        print("\n오류: 접근 거부 (gated). HF 라이선스 동의 + 로그인을 확인하세요.", file=sys.stderr)
        print("  https://huggingface.co/fishaudio/openaudio-s1-mini", file=sys.stderr)
    raise
print(f"\n다운로드 완료: {local_dir}")
PYEOF

# ── 5. 핵심 파일 검증
echo ""
echo "[5/5] 다운로드 검증..."
MISSING=0
for f in "codec.pth" "config.json"; do
    if [ -f "$DEST/$f" ]; then
        echo "  ✓ $f ($(du -sh "$DEST/$f" | cut -f1))"
    else
        echo "  ✗ $f — 누락!"
        MISSING=$((MISSING + 1))
    fi
done
# llama 체크포인트(모델 가중치) — 파일명이 버전마다 다를 수 있어 패턴 확인
if ls "$DEST"/*.pth "$DEST"/*.safetensors >/dev/null 2>&1; then
    echo "  ✓ 모델 가중치 ($(ls "$DEST"/*.pth "$DEST"/*.safetensors 2>/dev/null | wc -l)개)"
else
    echo "  ✗ 모델 가중치(.pth/.safetensors) 누락!"
    MISSING=$((MISSING + 1))
fi

if [ "$MISSING" -gt 0 ]; then
    echo ""
    echo "오류: 파일 ${MISSING}개 누락. 스크립트를 다시 실행하세요."
    exit 1
fi

# fish-speech-1.5는 롤백 자산으로 보존 (삭제하지 않음)
if [ -d "$PROJECT_ROOT/checkpoints/fish-speech-1.5" ]; then
    echo "  ℹ checkpoints/fish-speech-1.5 보존됨 (롤백용, ADR-0005)"
fi

# ── 완료 메시지
echo ""
echo "========================================"
echo "  설치 완료! 다음 단계:"
echo "========================================"
echo ""
echo "  1. fish-speech 컨테이너 (재)시작"
echo "     docker compose -f env/docker-compose.yml up -d fish-speech"
echo ""
echo "  2. 모델 로딩 대기(~3분) 및 헬스 확인"
echo "     docker compose -f env/docker-compose.yml ps        # fish-speech → healthy"
echo "     docker compose -f env/docker-compose.yml logs -f fish-speech"
echo ""
echo "  3. 음성 자산 등록 (녹음을 assets/voices_raw/에 두고)"
echo "     docker compose -f env/docker-compose.yml exec ai_worker \\"
echo "       python -m tools.prepare_voice --input assets/voices_raw/내목소리.wav --key default --label '기본'"
echo ""
echo "  4. TTS 테스트"
echo "     docker compose -f env/docker-compose.yml exec ai_worker python test/test_fish_speech.py"
echo ""
