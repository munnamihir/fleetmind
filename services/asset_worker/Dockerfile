FROM python:3.12-slim
WORKDIR /app
COPY services/asset_worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/common /app/common
COPY services/asset_worker /app/asset_worker
ENV PYTHONPATH=/app/common:/app/asset_worker
CMD ["python", "-m", "app.main"]
