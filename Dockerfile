FROM python:3.12-slim

# 시스템 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 파이썬 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# 마이그/정적/서버 기동
CMD ["sh","-lc", "\
    python manage.py migrate && \
    python manage.py collectstatic --noinput && \
    gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60 \
    "]
