# Playwright base image includes Chromium + OS deps for session validation.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Image already has uid 1000 (pwuser); reuse it instead of creating another.
RUN mkdir -p /app/outputs/salesnav /app/app/linkedin/outputs /app/app/salesnav/outputs /app/app/profile_extractor/outputs \
    && chown -R pwuser:pwuser /app
USER pwuser

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
