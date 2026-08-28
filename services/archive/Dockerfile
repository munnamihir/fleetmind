FROM python:3.12-slim
WORKDIR /app
COPY services/archive/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/common /app/common
COPY services/archive /app/archive
ENV PYTHONPATH=/app/common:/app/archive
CMD ["python", "-m", "app.main"]
