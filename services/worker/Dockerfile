FROM python:3.12-slim
WORKDIR /app
COPY services/worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/common /app/common
COPY services/worker /app/worker
ENV PYTHONPATH=/app/common:/app/worker
CMD ["python", "-m", "app.main"]
