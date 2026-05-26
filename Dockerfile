FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway Cron 通过 CMD 启动主脚本
CMD ["python", "main.py"]
