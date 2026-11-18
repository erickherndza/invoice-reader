FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# No corre como root
RUN useradd --system --uid 10001 --no-create-home app && chown -R app /app
USER app

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/health', timeout=3)"

# Con rate limit en PostgreSQL ya se puede usar más de un worker
CMD ["sh", "-c", "exec gunicorn -w ${WEB_CONCURRENCY:-2} --threads 4 -t 60 -b 0.0.0.0:${PORT} wsgi:app"]
