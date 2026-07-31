"""
Helena Studio MCP Server — Python (로컬/WSL/phone)

parksy-audio MCP voice 패턴 계승.
온디바이스 MCP 서버: 다이어그램 렌더링, 음성 더빙, SVG 합성.
"""

import json
import asyncio
from pathlib import Path

# MCP 도구 정의
TOOLS = [
    {
        "name": "render_diagram",
        "description": "Mermaid 다이어그램을 SVG로 렌더링 (온디바이스)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Mermaid 다이어그램 코드"},
                "theme": {"type": "string", "enum": ["default", "dark", "forest"], "default": "default"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "voice_dub",
        "description": "텍스트 → RVC 음성 더빙 트랙 생성 (온디바이스)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "더빙할 텍스트"},
                "voice": {"type": "string", "default": "parksy"},
                "output_format": {"type": "string", "enum": ["wav", "mp3"], "default": "wav"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "compose_page",
        "description": "SVG/HTML 조각을 웹페이지로 합성",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "components": {"type": "array", "items": {"type": "string"}},
                "template": {"type": "string", "default": "default"}
            },
            "required": ["title", "components"]
        }
    },
    {
        "name": "fetch_fridge",
        "description": "냉장고(dtslib1979)에서 자산 가져오기",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "냉장고 레포 이름 (예: parksy-audio)"},
                "path": {"type": "string", "description": "레포 내 경로"}
            },
            "required": ["repo"]
        }
    }
]


class HelenaMCP:
    """Helena Studio MCP Server"""

    def __init__(self):
        self.name = "helena-studio-mcp"
        self.version = "0.1.0"

    async def handle_request(self, method: str, params: dict = None) -> dict:
        if method == "tools/list":
            return {"tools": TOOLS}

        if method == "tools/call":
            tool_name = params.get("name") if params else None
            arguments = params.get("arguments", {}) if params else {}

            # TODO: Boss가 실제 도구 구현 — 현재는 구조만
            return {
                "result": f"[placeholder] {tool_name} 호출됨. "
                          f"인자: {json.dumps(arguments, ensure_ascii=False)[:200]}",
                "tool": tool_name,
                "status": "scaffold"
            }

        return {"error": f"Unknown method: {method}"}

    def run_stdio(self):
        """STDIO 모드 — Claude Code 직접 연결용"""
        import sys
        print(f"[Helena MCP] {self.name} v{self.version} — STDIO mode (scaffold)", file=sys.stderr)
        print("[Helena MCP] Waiting for MCP requests...", file=sys.stderr)

        for line in sys.stdin:
            try:
                request = json.loads(line.strip())
                result = asyncio.run(self.handle_request(
                    request.get("method", ""),
                    request.get("params")
                ))
                print(json.dumps(result), flush=True)
            except Exception as e:
                print(json.dumps({"error": str(e)}), flush=True)


if __name__ == "__main__":
    server = HelenaMCP()
    server.run_stdio()
