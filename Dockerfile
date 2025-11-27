FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first for better layer caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files (excluding .dockerignore patterns)
COPY . .

# Create cron job for daily Netsuite import at midnight
# The cron job will run the Python script directly
RUN echo "0 0 * * * cd /app && /usr/local/bin/python3 run_cron_import.py >> /var/log/cron.log 2>&1" > /etc/cron.d/netsuite-import && \
    chmod 0644 /etc/cron.d/netsuite-import && \
    crontab /etc/cron.d/netsuite-import && \
    touch /var/log/cron.log

# Expose port
EXPOSE 5000

# Set environment variables with defaults
ENV DB_HOST=localhost \
    DB_PORT=5432 \
    DB_USER=postgres \
    DB_PASSWORD="" \
    DB_NAME=offline \
    FLASK_PORT=5000

# Create startup script to run both cron and gunicorn
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Start cron daemon in foreground mode\n\
cron\n\
\n\
# Run gunicorn in foreground\n\
exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app\n\
' > /app/start.sh && chmod +x /app/start.sh

# Make the cron import script executable
RUN chmod +x /app/run_cron_import.py

# Run the startup script
CMD ["/app/start.sh"]