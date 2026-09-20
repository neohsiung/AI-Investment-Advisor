# ── Builder ──────────────────────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.11-slim-bookworm AS builder

RUN pip install uv
WORKDIR /workspace

RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1

# Which optional-dependency groups to bake in (see [project.optional-dependencies]).
#
# The default set is what the application actually imports at runtime:
#   memory        llama_index / mem0 — imported eagerly by llama_index_service
#   dspy          imported by the agent factory
#   channels-line imports as `linebot`, used by the LINE adapter
#   obs           OpenTelemetry exporters
#
# Deliberately NOT default: `forecast` (~900MB of PyTorch), `optimize`
# (cvxpy/scikit-learn — currently imported by nothing), `scrape` (playwright +
# a browser), and `dev` (pytest/bandit/safety, which have no business in a
# production image).
#
# 預設只裝執行期真正會 import 的 extras；torch、cvxpy、playwright 與測試工具不裝。
ARG PYTHON_EXTRAS="memory,dspy,channels-line,obs"

COPY pyproject.toml uv.lock ./

# torch, when requested, must come from PyTorch's CPU index FIRST.
#
# `timesfm[torch]` otherwise resolves to a CUDA build — measured 2026-08-14:
# torch 2.13.0+cu130 on aarch64, dragging in 2.9GB of `nvidia/*` libraries next
# to 897MB of torch, for a timesfm package that is itself 308KB. No container
# here has an NVIDIA GPU, so those 2.9GB can never execute; they filled the
# 63GB Docker VM disk and blocked every rebuild.
#
# Two steps rather than one resolve: the PyTorch index also mirrors unrelated
# packages at older versions and uv takes the first index carrying a name, so
# pointing the whole install at it fails to resolve. Installing torch alone
# from that index leaves it satisfied at `2.13.0+cpu`, and the second resolve
# adds no nvidia wheels.
#
# This step is now skipped entirely unless `forecast` is in PYTHON_EXTRAS —
# which by default it is not.
#
# 僅在啟用 forecast extra 時才安裝 torch，且強制走 CPU index。
RUN uv venv /opt/venv && \
    if echo ",${PYTHON_EXTRAS}," | grep -q ",forecast,"; then \
        echo "Installing CPU-only torch for the 'forecast' extra..." && \
        uv pip install --python /opt/venv --no-cache \
            --index-url https://download.pytorch.org/whl/cpu torch==2.13.0+cpu ; \
    fi

# Dependencies, resolved FROM THE LOCKFILE.
#
# This was `uv pip install -r pyproject.toml`, which ignores uv.lock entirely and
# re-resolves every dependency against PyPI on each build. Two consequences:
#
#   * builds were not reproducible — the same commit could produce different
#     transitive versions depending on when it was built;
#   * they were slow. A full re-resolve of ~50 direct dependencies took long
#     enough that a 40-minute build timeout killed it, while the lockfile that
#     would have made it fast sat unused. uv.lock had also drifted out of sync
#     (it was missing pydantic-settings entirely) with nothing to detect that,
#     precisely because nothing read it.
#
# `uv export --locked` FAILS if uv.lock disagrees with pyproject.toml, so a stale
# lock now breaks the build loudly instead of being silently bypassed. Run
# `uv lock` after changing dependencies.
#
# 原本用 -r pyproject.toml 安裝，完全忽略 uv.lock 並每次向 PyPI 重新解析：
# 建置不可重現且緩慢（曾因此被 40 分鐘 timeout 殺掉），而能讓它變快的 lock 檔
# 卻無人使用——也正因無人使用，lock 檔漂移（缺少 pydantic-settings）沒被發現。
# --locked 會在 lock 與 pyproject 不一致時讓建置直接失敗，改相依後請執行 uv lock。
RUN EXTRA_FLAGS="" && \
    for e in $(echo "${PYTHON_EXTRAS}" | tr ',' ' '); do \
        [ -n "$e" ] && EXTRA_FLAGS="$EXTRA_FLAGS --extra $e" ; \
    done && \
    echo "uv export --locked $EXTRA_FLAGS" && \
    uv export --locked --no-emit-project --no-hashes $EXTRA_FLAGS \
        -o /tmp/requirements.txt && \
    uv pip install --python /opt/venv --no-cache -r /tmp/requirements.txt

# ── Runner ───────────────────────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /workspace

# ffmpeg is required by pydub (podcast transcription); curl by the healthcheck.
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system appgroup && \
    adduser --system --group --home /home/appuser appuser

ENV HOME=/home/appuser

COPY --from=builder /opt/venv /opt/venv

COPY ./services/mcp_server /workspace/services/mcp_server
COPY ./src /workspace/src
COPY ./prompts /workspace/prompts
COPY ./config /workspace/config
COPY ./workspace /workspace/workspace
COPY ./alembic.ini /workspace/alembic.ini
COPY ./alembic /workspace/alembic
COPY ./scripts /workspace/scripts

USER root
RUN mkdir -p /workspace/data /workspace/logs && \
    chown -R appuser:appgroup /workspace /home/appuser
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn services.mcp_server.src.app.main:app --host 0.0.0.0 --port 8000"]
