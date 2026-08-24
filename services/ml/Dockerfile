FROM python:3.12-slim
WORKDIR /app
COPY services/ml/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/common /app/common
COPY services/ml /app/ml
ENV PYTHONPATH=/app/common:/app/ml
CMD ["python", "-m", "app.main"]
