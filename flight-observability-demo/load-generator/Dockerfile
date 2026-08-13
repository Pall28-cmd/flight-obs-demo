FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY generate_traffic.py .
CMD ["python", "generate_traffic.py"]
