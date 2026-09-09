FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/platform/pyproject.toml ./pyproject.toml
COPY services/platform/src ./src
COPY infra/database ./infra/database

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "alos.main:app", "--host", "0.0.0.0", "--port", "8000"]
