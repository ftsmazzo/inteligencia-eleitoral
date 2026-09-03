FROM python:3.12-slim
WORKDIR /app
COPY mcp/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp/app.py /app/app.py
COPY mcp/mcp_packs.py /app/mcp_packs.py
COPY mcp/apura /app/apura
COPY mcp/gestao /app/gestao
COPY mcp/static /app/static
COPY sql/patch_mcp_tokens.sql /app/sql/patch_mcp_tokens.sql
COPY sql/patch_apura.sql /app/sql/patch_apura.sql
COPY sql/patch_gestao.sql /app/sql/patch_gestao.sql
COPY sql/patch_gestao_v2.sql /app/sql/patch_gestao_v2.sql
COPY sql/patch_partido_linha.sql /app/sql/patch_partido_linha.sql
COPY sql/patch_acervo.sql /app/sql/patch_acervo.sql
COPY sql/patch_analitico.sql /app/sql/patch_analitico.sql
COPY sql/patch_pedido_demo.sql /app/sql/patch_pedido_demo.sql
COPY sql/patch_contas_resumo.sql /app/sql/patch_contas_resumo.sql
COPY sql/patch_rede_complementar_api.sql /app/sql/patch_rede_complementar_api.sql
COPY sql/patch_nominata_cargo_geral.sql /app/sql/patch_nominata_cargo_geral.sql
COPY sql/patch_municipio_api.sql /app/sql/patch_municipio_api.sql
COPY sql/api.sql /app/sql/api.sql
COPY mcp/radar_client.py /app/radar_client.py
COPY mcp/clima_motores.py /app/clima_motores.py
COPY mcp/radar /app/radar
COPY sql/patch_radar.sql /app/sql/patch_radar.sql
COPY sql/patch_radar_v2.sql /app/sql/patch_radar_v2.sql
COPY mcp/seed /app/seed
ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
