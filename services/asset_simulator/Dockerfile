FROM python:3.12-slim
WORKDIR /app
COPY services/asset_simulator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/asset_simulator /app/asset_simulator
ENV PYTHONPATH=/app/asset_simulator
CMD ["python", "-m", "app.main"]
