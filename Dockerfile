FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg is required (imageio-ffmpeg bundles a binary, but a system ffmpeg
# is used by ensure_thumbnail and some pipeline stages).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY avatar-production-mib/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY avatar-production-mib/ ./

# Spaces convention: bind 0.0.0.0:7860
EXPOSE 7860

# Persistent state (jobs, config, uploads) lives under /data on hosts that
# provide it; MIB_DATA_DIR redirects config+output there when set.
ENV MIB_DATA_DIR=/data

CMD ["python", "web_app.py"]
