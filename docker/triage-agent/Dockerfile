FROM debian:12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash agent

USER agent

ENV PATH="/home/agent/.local/bin:/home/agent/.opencode/bin:${PATH}"

RUN curl -fsSL https://claude.ai/install.sh | bash

RUN mkdir -p /home/agent/.claude/

RUN curl -fsSL https://opencode.ai/install | bash

RUN git config --global --add safe.directory '*'

WORKDIR /workspace
