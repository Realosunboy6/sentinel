FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN addgroup --system sentinel && adduser --system --ingroup sentinel sentinel

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .
RUN SECRET_KEY=collect-static-only \
    DATABASE_URL=sqlite:////tmp/collect-static.sqlite3 \
    DEBUG=False \
    python manage.py collectstatic --noinput && \
    chown -R sentinel:sentinel /app

USER sentinel

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz',timeout=3)"

CMD ["sh", "-c", "gunicorn sentinel.wsgi:application --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --access-logfile - --error-logfile -"]
