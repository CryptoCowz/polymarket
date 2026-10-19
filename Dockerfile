FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

COPY pyproject.toml README.md config.yaml ./
COPY src ./src
COPY research ./research
COPY docs ./docs
COPY scripts ./scripts
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["python", "-m", "aroonbot"]
