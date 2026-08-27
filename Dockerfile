FROM python:3.12-slim
WORKDIR /app
COPY mcp/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp/app.py /app/app.py
COPY mcp/apura /app/apura
COPY mcp/static /app/static
COPY sql/patch_mcp_tokens.sql /app/sql/patch_mcp_tokens.sql
COPY sql/patch_apura.sql /app/sql/patch_apura.sql
COPY sql/patch_partido_linha.sql /app/sql/patch_partido_linha.sql
COPY sql/patch_acervo.sql /app/sql/patch_acervo.sql
COPY sql/api.sql /app/sql/api.sql
COPY mcp/radar_client.py /app/radar_client.py
ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
