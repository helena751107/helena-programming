# Helena Studio — WSL/PC 로컬 실행용 Docker 이미지
FROM python:3.11-slim

WORKDIR /app

COPY mcp/requirements.txt . 2>/dev/null || true
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

COPY mcp/ .

EXPOSE 3456
CMD ["python", "mcp_server.py"]
