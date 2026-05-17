FROM node:22-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
  build-essential \
  git \
  curl \
  jq \
  ripgrep \
  && rm -rf /var/lib/apt/lists/*

# Install uv. It manages this repo's Python toolchain and virtualenv.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
  && mv /root/.local/bin/uv /usr/local/bin/uv \
  && mv /root/.local/bin/uvx /usr/local/bin/uvx

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && apt-get update && apt-get install -y gh \
  && rm -rf /var/lib/apt/lists/*

# Build-args for UID/GID alignment: sandcastle docker build-image
# defaults these to the host user's UID/GID so image-built files
# and bind-mounted files share an owner without runtime chown.
ARG AGENT_UID=1000
ARG AGENT_GID=1000

# Rename the base image's "node" user to "agent" and align UID/GID.
# On macOS, AGENT_GID is commonly 20, which already exists in Debian.
RUN usermod -u $AGENT_UID -g $AGENT_GID -d /home/agent -m -l agent node \
  && chmod -R a+rwX /home/agent

# Install Codex CLI (run as root before USER agent)
RUN npm install -g @openai/codex

USER ${AGENT_UID}:${AGENT_GID}

WORKDIR /home/agent

ENV UV_PYTHON_INSTALL_DIR="/home/agent/workspace/.uv-python"
ENV PATH="/home/agent/workspace/.venv/bin:$PATH"

# In worktree sandbox mode, Sandcastle bind-mounts the git worktree at /home/agent/workspace
# and overrides the working directory to /home/agent/workspace at container start.
# Structure your Dockerfile so that /home/agent/workspace can serve as the project root.
ENTRYPOINT ["sleep", "infinity"]
