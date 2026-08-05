#!/usr/bin/env python3
"""FreeCAD 파라메트릭 모델링 예제 — GitHub Actions에서 freecadcmd로 실행"""

import sys
import os

# freecadcmd는 FreeCAD 모듈을 내장하고 있음
try:
    import FreeCAD
    import Part
    import Mesh
except ImportError:
    print("⚠️  FreeCAD 모듈 없음. freecadcmd로 실행하세요: freecadcmd render.py")
    sys.exit(1)

os.makedirs("out", exist_ok=True)

# ── 예제: 파라메트릭 박스 ──
doc = FreeCAD.newDocument("HelenaPart")

# 파라메트릭 값 (환경변수로 오버라이드 가능)
width = float(os.environ.get("BOX_W", 50))
height = float(os.environ.get("BOX_H", 30))
depth = float(os.environ.get("BOX_D", 20))

box = doc.addObject("Part::Box", "Box")
box.Width = width
box.Height = height
box.Length = depth

doc.recompute()

# STL 출력
stl_path = os.path.join("out", f"box_{width}x{height}x{depth}.stl")
Mesh.export([box], stl_path)
print(f"✅ {stl_path}")

# STEP 출력
step_path = os.path.join("out", f"box_{width}x{height}x{depth}.step")
Part.export([box], step_path)
print(f"✅ {step_path}")

FreeCAD.closeDocument(doc.Name)
print("🎉 CAD 렌더링 완료")
