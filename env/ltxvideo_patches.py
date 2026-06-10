"""
ComfyUI-LTXVideo 호환성 패치 스크립트.
Dockerfile 빌드 시 git clone 직후 실행됨.

Patch 1 — pyramid_blending.py
  kornia 0.8.3에서 `pad`가 kornia.geometry.transform.pyramid에서 제거됨.
  모든 `pad(...)` 호출을 `F.pad(...)`로 교체.

Patch 2 — embeddings_connector.py
  standalone connector 파일(ltx-2-19b-embeddings_connector_distill_bf16.safetensors)은
  풀 체크포인트 없이 'video_embeddings_connector.*' 키만 가짐.
  AV prefix 감지를 audio_adaln_single.linear.weight 에만 의존하면
  connector 파일이 None으로 로드되어 'NoneType' is not callable 에러 발생.

Patch 3 — text_embeddings_connectors.py
  is_av 판별도 동일 이유로 audio_embeddings_connector prefix 존재 여부 추가 확인.
"""

import re
import pathlib

def patch1_pyramid_blending():
    p = pathlib.Path("pyramid_blending.py")
    t = p.read_text()
    t = re.sub(r"\n    pad,\n", "\n", t)
    t = t.replace("    image = pad(image,", "    image = F.pad(image,")
    t = t.replace("    images = pad(images,", "    images = F.pad(images,")
    p.write_text(t)
    print("Patch 1 applied: pyramid_blending.py (kornia pad -> F.pad)")


def patch2_embeddings_connector():
    p = pathlib.Path("embeddings_connector.py")
    t = p.read_text()
    old = (
        "    prefix = (\n"
        "        av_connector_prefix\n"
        '        if f"{_PREFIX_BASE}audio_adaln_single.linear.weight" in sd\n'
        "        else video_only_connector_prefix\n"
        "    )\n"
    )
    new = (
        "    _is_av_sd = (\n"
        '        f"{_PREFIX_BASE}audio_adaln_single.linear.weight" in sd\n'
        "        or any(k.startswith(av_connector_prefix) for k in sd)\n"
        "    )\n"
        "    prefix = av_connector_prefix if _is_av_sd else video_only_connector_prefix\n"
    )
    if old in t:
        p.write_text(t.replace(old, new))
        print("Patch 2 applied: embeddings_connector.py (AV prefix detection)")
    else:
        print("WARN Patch 2: pattern not found (already patched?)")


def patch3_text_embeddings_connectors():
    p = pathlib.Path("text_embeddings_connectors.py")
    t = p.read_text()
    old = '    is_av = f"{_PREFIX_BASE}audio_adaln_single.linear.weight" in sd\n'
    new = (
        '    _audio_connector_prefix = f"{_PREFIX_BASE}audio_embeddings_connector."\n'
        "    is_av = (\n"
        '        f"{_PREFIX_BASE}audio_adaln_single.linear.weight" in sd\n'
        "        or any(k.startswith(_audio_connector_prefix) for k in sd)\n"
        "    )\n"
    )
    if old in t:
        p.write_text(t.replace(old, new))
        print("Patch 3 applied: text_embeddings_connectors.py (is_av via audio prefix)")
    else:
        print("WARN Patch 3: pattern not found (already patched?)")


if __name__ == "__main__":
    patch1_pyramid_blending()
    patch2_embeddings_connector()
    patch3_text_embeddings_connectors()
