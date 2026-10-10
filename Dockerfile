FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY app app
COPY web web
COPY prompts prompts
RUN useradd --create-home --uid 10001 cunbo && mkdir /app/data && chown cunbo:cunbo /app/data
USER cunbo
ENV LOCAL_TRUST=0 CLIPFORGE_DATA=/app/data
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1","--no-proxy-headers"]
