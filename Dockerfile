# NAO TESTADO LOCALMENTE (sem Docker nesta maquina). Imagem unica para API e worker.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini ./
COPY data/demo ./data/demo
RUN pip install --no-cache-dir -e .
EXPOSE 18100
CMD ["uvicorn", "backend.app.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "18100"]
