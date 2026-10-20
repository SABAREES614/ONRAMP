FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --link-mode copy

COPY src ./src
COPY frontend ./frontend
COPY registries ./registries

ENV ONRAMP_DB=/data/onramp.db
ENV NEURO_SAN_URL=http://neuro-san:8080

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "onramp_neuro_san.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
