# ============================================================================
# Dockerfile Multi-Stage para o Câmbio Global
# ============================================================================

# Stage 1: Build & Dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Instala dependências de build se necessário
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime Image (Segurança & Non-Root)
FROM python:3.12-slim AS runner

WORKDIR /app

# Cria usuário não-root seguro
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Copia pacotes instalados do builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copia o código-fonte da aplicação
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup README.md pyproject.toml pytest.ini .env.example ./

# Cria diretório de persistência de dados
RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

CMD ["uvicorn", "src.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
