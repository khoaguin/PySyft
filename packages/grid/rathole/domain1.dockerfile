ARG PYTHON_VERSION="3.12"
FROM python:${PYTHON_VERSION}-bookworm
RUN apt update && apt install -y netcat-openbsd vim
WORKDIR /app
CMD ["python3", "-m", "http.server", "1001"]
EXPOSE 1001