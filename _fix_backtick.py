import os
lines = open(r'C:\Users\zq\PycharmProjects\AI_NOTE\frontend\src\pages\AppShell\SettingsView.tsx', 'r', encoding='utf-8').readlines()
for i, line in enumerate(lines):
    if 'fetch(/api/v1/system/embedding-model,' in line:
        # Replace with proper backtick-quoted URL
        bt = chr(96)  # backtick character
        lines[i] = line.replace(
            'fetch(/api/v1/system/embedding-model,',
            'fetch(' + bt + '/api/v1/system/embedding-model' + bt + ','
        )
        print(f'Fixed line {i+1}')
        break
open(r'C:\Users\zq\PycharmProjects\AI_NOTE\frontend\src\pages\AppShell\SettingsView.tsx', 'w', encoding='utf-8').write(''.join(lines))
print('Written')