FROM python:3.13-slim
WORKDIR /app
COPY *.py taxonomy.json ./
ENV PYTHONUNBUFFERED=1 PORT=8080 STUB_DB=/data/data.db
EXPOSE 8080
CMD ["python", "server.py"]
