/**
 * Helena Studio MCP Server — Vercel Serverless Endpoint
 *
 * MCP 프로토콜 엔드포인트. 웹에서 접근 가능한 MCP 도구들을 제공한다.
 * Vercel에 배포되어 항시 접근 가능.
 */

// 간소화된 HTTP → MCP 프록시 (Serverless)
export default async function handler(req, res) {
  res.setHeader('Content-Type', 'application/json');

  const { method, body } = req;

  // MCP 도구 목록
  const tools = [
    {
      name: 'render_diagram',
      description: 'Mermaid 다이어그램을 SVG로 렌더링',
      inputSchema: {
        type: 'object',
        properties: {
          code: { type: 'string', description: 'Mermaid 다이어그램 코드' },
          theme: { type: 'string', enum: ['default', 'dark', 'forest'], default: 'default' }
        },
        required: ['code']
      }
    },
    {
      name: 'compose_page',
      description: 'SVG/HTML 조각을 웹페이지로 합성',
      inputSchema: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          components: { type: 'array', items: { type: 'string' } }
        },
        required: ['title', 'components']
      }
    },
    {
      name: 'voice_dub',
      description: '텍스트 → RVC 음성 더빙 트랙 생성',
      inputSchema: {
        type: 'object',
        properties: {
          text: { type: 'string', description: '더빙할 텍스트' },
          voice: { type: 'string', default: 'parksy' }
        },
        required: ['text']
      }
    }
  ];

  // MCP 프로토콜 라우팅
  if (method === 'GET') {
    return res.json({
      service: 'helena-studio-mcp',
      version: '0.1.0',
      tools: tools.length,
      status: 'operational'
    });
  }

  if (method === 'POST') {
    try {
      const { method: mcpMethod, params } = typeof body === 'string' ? JSON.parse(body) : body;

      switch (mcpMethod) {
        case 'tools/list':
          return res.json({ tools });
        case 'tools/call':
          // TODO: 실제 도구 구현 — 구조만 제공
          return res.json({
            result: `[placeholder] ${params?.name} 호출됨. Boss 구현 예정.`,
            tool: params?.name
          });
        default:
          return res.status(400).json({ error: `Unknown method: ${mcpMethod}` });
      }
    } catch (e) {
      return res.status(400).json({ error: e.message });
    }
  }

  res.status(405).json({ error: 'Method not allowed' });
}
