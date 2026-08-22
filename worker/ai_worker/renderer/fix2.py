with open('layout.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix line 1550 (0-indexed: 1549)
for i in range(len(lines)):
    if i >= 1548 and i <= 1555 and 'anull[tts]' in lines[i]:
        # Replace anull[tts] → asplit=2[tts_key][tts_mix]
        lines[i] = lines[i].replace('anull[tts]', 'asplit=2[tts_key][tts_mix]')
        print(f"Fixed line {i+1}: {lines[i].strip()}")
    
    if i >= 1548 and i <= 1555 and '[tts]sidechaincompress' in lines[i]:
        # Replace [tts] → [tts_key]
        lines[i] = lines[i].replace('[tts]sidechaincompress', '[tts_key]sidechaincompress')
        print(f"Fixed line {i+1}: {lines[i].strip()}")
    
    if i >= 1548 and i <= 1555 and '[tts][bgm_ducked]' in lines[i]:
        # Replace [tts] → [tts_mix]
        lines[i] = lines[i].replace('[tts][bgm_ducked]', '[tts_mix][bgm_ducked]')
        print(f"Fixed line {i+1}: {lines[i].strip()}")

with open('layout.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed second location")
