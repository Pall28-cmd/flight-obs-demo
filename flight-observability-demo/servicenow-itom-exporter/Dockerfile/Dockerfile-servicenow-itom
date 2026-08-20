FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask prometheus-client

# Copy the ITOM generator and exporter
COPY servicenow_itom_extended.py /app/servicenow_itom_extended.py
COPY servicenow_itom_exporter.py /app/servicenow_itom_exporter.py

# Expose metrics port
EXPOSE 9095

# Start the exporter
CMD ["python", "servicenow_itom_exporter.py"]
