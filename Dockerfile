FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

COPY .claude/ ./.claude/
COPY examples/ ./examples/

ENV GRADIO_SERVER_NAME=0.0.0.0
EXPOSE 7860

CMD ["dpo-redact", "ui", "--host", "0.0.0.0", "--port", "7860"]
