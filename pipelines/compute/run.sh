#!/bin/bash
# 범용 컴퓨트 예제 — 환경 정보 출력 + 간단 벤치
# 이 스크립트를 수정하거나, Actions에서 command= 로 직접 명령어 전달 가능

set -e
mkdir -p out

echo "🖥️  GitHub Actions Runner 정보"
echo "=============================="
echo "CPU:   $(nproc) 코어"
echo "RAM:   $(free -h | awk '/Mem/{print $2}')"
echo "OS:    $(cat /etc/os-release | head -1)"
echo "Arch:  $(uname -m)"
echo "Disk:  $(df -h / | tail -1 | awk '{print $2}')"
echo ""

# 간단 CPU 벤치
echo "⚡ CPU 워밍업 (Python math)..."
python3 -c "
import math, time
t = time.time()
for i in range(10_000_000):
    math.sqrt(i)
print(f'1천만 sqrt: {time.time()-t:.2f}s')
"

# 결과 저장
echo "완료: $(date)" > out/result.txt
echo "Runner: $(uname -a)" >> out/result.txt
echo "RAM: $(free -h | awk '/Mem/{print $2}')" >> out/result.txt

echo ""
echo "✅ 결과: out/result.txt"
