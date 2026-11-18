FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
# 1 worker + hilos: el rate limit en memoria es por proceso
CMD gunicorn -w 1 --threads 8 -t 60 -b 0.0.0.0:${PORT} wsgi:app
