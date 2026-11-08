FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py taxonomy.json ./
# STUB_DB is only used when DATABASE_URL is unset (SQLite fallback; wiped on Render free).
ENV PYTHONUNBUFFERED=1 PORT=8080 STUB_DB=/app/data/data.db
EXPOSE 8080
CMD ["python", "server.py"]
