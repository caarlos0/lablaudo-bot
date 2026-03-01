FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim
ARG TARGETPLATFORM
RUN uv venv
ENTRYPOINT [ "uv", "run", "-m", "lablaudo" ]

COPY $TARGETPLATFORM/lablaudo*.whl /tmp/
RUN uv pip install /tmp/*.whl
