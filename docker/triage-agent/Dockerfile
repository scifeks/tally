FROM debian:12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       git \
       jq \
       tinyproxy \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash agent

USER agent

ENV PATH="/home/agent/.local/bin:/home/agent/.opencode/bin:${PATH}"

RUN curl -fsSL https://claude.ai/install.sh | bash

RUN mkdir -p /home/agent/.claude/

RUN curl -fsSL https://opencode.ai/install | bash \
    && cp /home/agent/.opencode/bin/opencode /home/agent/.local/bin/opencode

RUN mkdir -p /home/agent/.local/share/opencode \
             /home/agent/.local/state/opencode \
             /home/agent/.cache/opencode \
             /home/agent/.config/opencode

RUN git config --global --add safe.directory '*'

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/*
COPY opencode-permissions.json /etc/opencode/permissions.json
COPY triage-relay.sh /usr/local/bin/triage-relay
RUN chmod +x /usr/local/bin/triage-relay
USER agent

WORKDIR /workspace
