FROM python:3.12-slim
WORKDIR /app
COPY services/simulator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/simulator /app/simulator
ENV PYTHONPATH=/app/simulator
CMD ["python", "-m", "app.main"]
