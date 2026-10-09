FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ausearch reads host audit logs; journalctl reads mounted host journals.
RUN apt-get update \
    && apt-get install -y --no-install-recommends auditd systemd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Keep the image focused on the logger, not the whole repository.
COPY company/logger/ /app/company/logger/

CMD ["python3", "/app/company/logger/logger.py"]
