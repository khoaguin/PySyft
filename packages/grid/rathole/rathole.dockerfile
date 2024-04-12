ARG RATHOLE_VERSION="0.5.0"
ARG PYTHON_VERSION="3.12"

# build with rust and clone the rathole repo
FROM rust as build
ARG RATHOLE_VERSION
ARG FEATURES
RUN apt update && apt install -y git
RUN git clone -b v${RATHOLE_VERSION} https://github.com/rapiz1/rathole

# build rathole
WORKDIR /rathole
RUN cargo build --locked --release --features ${FEATURES:-default}

# running a Python application alongside the "rathole" Rust application
FROM python:${PYTHON_VERSION}-bookworm
ARG RATHOLE_VERSION
ENV MODE="client"
COPY --from=build /rathole/target/release/rathole /app/rathole
RUN apt update && apt install -y netcat-openbsd vim
WORKDIR /app
COPY ./start-client.sh /app/start-client.sh
RUN chmod +x /app/start-client.sh
COPY ./start-server.sh /app/start-server.sh
RUN chmod +x /app/start-server.sh
COPY ./client.toml /app/client.toml
COPY ./server.toml /app/server.toml
COPY ./nginx.conf /etc/nginx/conf.d/default.conf

CMD ["sh", "-c", "/app/start-$MODE.sh"]
EXPOSE 2333/udp
EXPOSE 2333