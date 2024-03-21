ARG PYTHON_VERSION="3.12"
ARG UV_VERSION="0.1.22-r0"
ARG TORCH_VERSION="2.2.1"

# ==================== [BUILD STEP] Python Dev Base ==================== #
FROM cgr.dev/chainguard/wolfi-base as syft_deps

ARG PYTHON_VERSION
ARG UV_VERSION
ARG TORCH_VERSION

# Setup Python DEV
RUN apk update && apk upgrade && \
    apk add build-base gcc python-$PYTHON_VERSION-dev-default uv=$UV_VERSION

WORKDIR /root/app

# keep static deps separate to have each layer cached independently
# if amd64 then we need to append +cpu to the torch version
# limitation of uv - https://github.com/astral-sh/uv/issues/2541
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    uv venv && \
    ARCH=$(arch | sed s/aarch64/arm64/ | sed s/x86_64/amd64/) && \
    if [[ "$ARCH" = "amd64" ]]; then TORCH_VERSION="$TORCH_VERSION+cpu"; fi && \
    uv pip install torch==$TORCH_VERSION --index-url https://download.pytorch.org/whl/cpu

RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    uv pip install jupyterlab==4.1.5

COPY --chown=nonroot:nonroot \
    syft/setup.py syft/setup.cfg syft/pyproject.toml ./syft/

COPY --chown=nonroot:nonroot \
    syft/src/syft/VERSION ./syft/src/syft/

RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    uv pip install  -e ./syft[data_science,telemetry] && \
    uv pip freeze | grep ansible | xargs uv pip uninstall


# ==================== [Final] Setup Syft Server ==================== #

FROM cgr.dev/chainguard/wolfi-base as backend

ARG PYTHON_VERSION
ARG UV_VERSION

RUN apk update && apk upgrade && \
    apk add git bash python-$PYTHON_VERSION-default uv=$UV_VERSION

WORKDIR /root/app/

# Copy pre-built jupyterlab, syft dependencies
COPY --from=syft_deps /root/app/.venv .venv

# copy grid
COPY grid/backend/grid grid/backend/worker_cpu.dockerfile ./grid/

# copy syft
COPY syft ./syft/

# Update environment variables
ENV \
    PATH="/root/app/.venv/bin:$PATH" \
    APPDIR="/root/app" \
    NODE_NAME="default_node_name" \
    NODE_TYPE="domain" \
    SERVICE_NAME="backend" \
    RELEASE="production" \
    DEV_MODE="False" \
    DEBUGGER_ENABLED="False" \
    CONTAINER_HOST="docker" \
    OBLV_ENABLED="False" \
    OBLV_LOCALHOST_PORT=3030 \
    DEFAULT_ROOT_EMAIL="info@openmined.org" \
    DEFAULT_ROOT_PASSWORD="changethis" \
    STACK_API_KEY="changeme" \
    MONGO_HOST="localhost" \
    MONGO_PORT="27017" \
    MONGO_USERNAME="root" \
    MONGO_PASSWORD="example"

CMD ["bash", "./grid/start.sh"]
