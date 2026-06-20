FROM python:3.12-alpine

RUN apk add --no-cache bash bash-completion

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY app.py index.html ./

EXPOSE 7681

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7681"]
