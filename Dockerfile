FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY grok_org_os ./grok_org_os

RUN pip install --no-cache-dir -e .

EXPOSE 8000

ENV DATABASE_URL=sqlite:///./data/grok_org_os.db
ENV HOST=0.0.0.0
ENV PORT=8000

RUN mkdir -p /app/data

CMD ["uvicorn", "grok_org_os.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
