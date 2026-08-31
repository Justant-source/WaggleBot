import re

with open('layout.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: anull[tts] → asplit=2[tts_key][tts_mix]
old_filter_1 = (
    'f"[1:a]anull[tts];"\n'
    '                    f"[2:a]volume=0.15,aloop=loop=-1:size=2e+09[bgm_loop];"\n'
    '                    f"[bgm_loop][tts]sidechaincompress=threshold=0.03:ratio=9:attack=50:release=400:makeup=1[bgm_ducked];"\n'
    '                    f"[tts][bgm_ducked]amix=inputs=2:duration=first:normalize=0[mixed];"\n'
    '                    f"[mixed]loudnorm=I=-14:TP=-1:LRA=7[aout]"'
)

new_filter = (
    'f"[1:a]asplit=2[tts_key][tts_mix];"\n'
    '                    f"[2:a]volume=0.15,aloop=loop=-1:size=2e+09[bgm_loop];"\n'
    '                    f"[bgm_loop][tts_key]sidechaincompress=threshold=0.03:ratio=9:attack=50:release=400:makeup=1[bgm_ducked];"\n'
    '                    f"[tts_mix][bgm_ducked]amix=inputs=2:duration=first:normalize=0[mixed];"\n'
    '                    f"[mixed]loudnorm=I=-14:TP:-1:LRA=7[aout]"'
)

content = content.replace(old_filter_1, new_filter)

with open('layout.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed layout.py")
