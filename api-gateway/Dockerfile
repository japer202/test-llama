FROM python:3.11-slim

WORKDIR /app

# 创建日志和数据库目录
RUN mkdir -p /app/logs /app/database

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY index.py .

CMD ["python", "index.py"]