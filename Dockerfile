FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    python-telegram-bot>=21.0 \
    pydantic>=2.12.5 \
    pydantic-settings>=2.12.0 \
    python-dotenv>=1.0.0 \
    langchain>=0.3.0 \
    langchain-google-genai>=2.0.0 \
    langchain-openai>=0.2.0 \
    langsmith>=0.1.0 \
    jinja2>=3.1.2

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
