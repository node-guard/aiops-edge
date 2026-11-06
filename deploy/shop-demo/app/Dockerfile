# syntax=docker/dockerfile:1
# Build from this directory:
#   docker build -t shop-demo:0.1.0 .
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 shop \
    && useradd --system --uid 10001 --gid shop --no-create-home shop

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=shop:shop shop_demo.py logging.json ./

USER 10001:10001
EXPOSE 8080

CMD ["python", "-m", "uvicorn", "shop_demo:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--log-config", "/app/logging.json", "--timeout-graceful-shutdown", "5"]
