---
name: docker-compose-safe-edit
description: |
  安全編輯 docker-compose.yml 的標準化流程。避免因 YAML 結構性錯誤
  （如 env_file/environment 合併、縮排不一致、遺失必要環境變數）導致
  容器啟動失敗。
  觸發時機：
  (1) 修改任何 docker-compose*.yml 文件前
  (2) 新增/移除 Docker 服務環境變數前
  (3) 偵測到 `env file ... not found` 或 YAML parse error 時
---

# Docker Compose Safe Edit Skill

## Problem Statement

Docker Compose YAML files have strict structural rules. Common AI editing mistakes include:
1. **env_file / environment merge**: When editing `environment:` variables near `env_file:`, the `environment:` keyword gets deleted and variables become file paths.
2. **Variable deletion**: When using search-and-replace to add a new env var, adjacent lines (e.g., `DB_HOST`, `NODE_ENV`) get accidentally removed.
3. **Indentation corruption**: Mixing 2-space/4-space indentation breaks YAML parsing.

## Mandatory Pre-Edit Checklist

Before editing any `docker-compose*.yml` file, the agent MUST:

### Step 1: Snapshot the Service Block
```
view_file the entire service block you intend to edit (from `service_name:` to the next service or end of file).
Record the EXACT line numbers.
```

### Step 2: Identify Structural Boundaries
For each service, confirm the presence of these YAML keys (if applicable):
- `env_file:` — list of `.env` file paths (each starts with `- `)
- `environment:` — list of `KEY=VALUE` pairs (each starts with `- `)
- `volumes:`, `depends_on:`, `healthcheck:`, `networks:`

**CRITICAL**: `env_file:` and `environment:` are SEPARATE top-level keys under a service. They must NEVER be merged. A correct structure looks like:

```yaml
  service_name:
    env_file:
      - .env
    environment:
      - NODE_ENV=production
      - REDIS_URL=redis://redis:6379/0
```

An INCORRECT (broken) structure looks like:

```yaml
  service_name:
    env_file:
      - .env
      - REDIS_URL=redis://redis:6379/0   # ← WRONG: this is treated as a file path!
```

### Step 3: Make Minimal, Targeted Edits
- Only modify the lines that need changing.
- **NEVER use `multi_replace_file_content` with large `TargetContent` blocks that span `env_file:` → `environment:` boundaries.** This is the #1 cause of structural corruption.
- If adding a new env var, target ONLY the `environment:` block.
- If modifying `env_file:`, target ONLY the `env_file:` block.

### Step 4: Post-Edit Validation (MANDATORY)
After ANY edit to a docker-compose file, ALWAYS run:

```bash
docker compose -f <filename> config --quiet
```

If it fails, immediately:
1. View the affected service block
2. Check that `env_file:` and `environment:` are separate keys
3. Verify no env vars are missing (compare against pre-edit snapshot)

### Step 5: Deep Validation
Run the following to confirm all critical env vars are present:

```bash
docker compose -f <filename> config 2>&1 | grep -E 'NODE_ENV|DB_HOST|DATABASE_URL|OTEL_SERVICE|REDIS_URL'
```

Compare the output to your pre-edit snapshot. If any variable is missing, restore it immediately.

## Known Gotchas for This Project

### 1. Four Services Require `DATABASE_URL`
`worker_1` and `worker_2` MUST have:
```yaml
- DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@postgres:5432/${DB_NAME}
```
`mcp_server` and `scheduler` use `DB_HOST=postgres` instead.

### 2. All Python Services Need `NODE_ENV=production`
This controls behavior in the application layer. It must be present in `mcp_server`, `scheduler`, `worker_1`, `worker_2`.

### 3. OTEL Triple
All Python services need these three together:
```yaml
- OTEL_SERVICE_NAME=<unique_service_name>
- OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
- OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

## Rollback Strategy
If the docker-compose file is corrupted beyond easy repair:
```bash
git checkout -- docker-compose.prod.yml
```
Then re-apply only the intended changes, one service block at a time.

## Reference: Correct Service Environment Structure

```yaml
  worker_1:
    env_file:        # ← Block 1: file references
      - .env
    environment:     # ← Block 2: inline variables (SEPARATE key!)
      - NODE_ENV=production
      - WORKER_ID=worker-1
      - WORKER_CONCURRENCY=2
      - QUEUE_REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@postgres:5432/${DB_NAME}
      - OTEL_SERVICE_NAME=worker_1_prod
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
      - OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```
