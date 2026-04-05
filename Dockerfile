FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements_minimal.txt ./
RUN pip install --no-cache-dir -r requirements_minimal.txt

COPY . .

EXPOSE 5000

CMD ["python", "run.py"]
