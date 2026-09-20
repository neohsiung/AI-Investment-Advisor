"""
Deployment invariants that are easy to break silently by editing compose.

Both failures below have actually happened in this milestone series, by the same
mechanism: an edit that deleted a *range* of YAML between two service names took
an unrelated service with it.

  * removing `scraper` (range `scraper:` → `nginx:`) deleted the `ngrok` service
    that sat between them. `./start.sh tunnel` then passed its own guards and
    died with "no such service: ngrok".
  * removing `scraper` from the dev file (range `scraper:` → `volumes:`) deleted
    the six `profiles: [observability]` stamps sitting in that gap, quietly
    putting the whole SigNoz stack back into the default boot.

These are structural facts about the deployment, so they are asserted by parsing
the compose files rather than by running docker.

以下兩個問題都真實發生過，且成因相同：刪除兩個服務名稱之間的 YAML 範圍時，
把夾在中間的其他服務／設定一併刪掉。故以解析 compose 檔的方式固定這些不變量。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PROD = Path("docker-compose.prod.yml")
DEV = Path("docker-compose.yml")

# Containers that must never start by default on a single box.
OPT_IN_ONLY = {
    "ngrok": "tunnel",
    "n8n": "n8n",
    "clickhouse": "observability",
    "zookeeper-1": "observability",
    "signoz": "observability",
    "otel-collector": "observability",
    "init-clickhouse": "observability",
    "schema-migrator-sync": "observability",
    "schema-migrator-async": "observability",
}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _services(path: Path) -> dict:
    return _load(path).get("services", {}) or {}


class TestProdCompose:

    def test_core_services_present(self):
        """The stack cannot boot without these."""
        svc = _services(PROD)
        for name in ("mcp_server", "frontend", "postgres", "redis", "worker", "celery_beat", "nginx"):
            assert name in svc, f"{name} is missing from {PROD}"

    def test_ngrok_exists_and_is_opt_in(self):
        svc = _services(PROD)
        assert "ngrok" in svc, (
            "the ngrok service is gone. It was deleted once already by an edit "
            "that removed the range between `scraper:` and `nginx:` — ngrok sat "
            "in that gap. ./start.sh tunnel cannot work without it."
        )
        assert svc["ngrok"].get("profiles") == ["tunnel"]

    def test_tunnel_targets_the_webhook_only_vhost(self):
        """
        Pointing ngrok at :80 publishes the unauthenticated dashboard and the
        whole /api/ surface. :8080 is the vhost that exposes only /webhook/ and
        /callback/.
        指向 :80 會把無登入的儀表板與 /api/ 對外開放；:8080 只公開 webhook/callback。
        """
        command = _services(PROD)["ngrok"].get("command", "")
        assert "advisor_prod_gateway:8080" in command, (
            f"ngrok must target the webhook-only vhost on :8080, got: {command!r}"
        )
        assert "advisor_prod_gateway:80 " not in f"{command} ", "ngrok must not target :80"

    @pytest.mark.parametrize("name,profile", sorted(OPT_IN_ONLY.items()))
    def test_optional_services_are_profiled(self, name, profile):
        svc = _services(PROD)
        if name not in svc:
            pytest.skip(f"{name} not defined in {PROD}")
        assert svc[name].get("profiles") == [profile], (
            f"{name} must sit behind `profiles: [{profile}]` so it never starts "
            "by default on a single box"
        )

    def test_no_pip_install_at_container_start(self):
        """
        The API command used to `pip install itsdangerous` on every start. The
        package is no longer a dependency and `uv venv` ships no pip, so the
        container could only fail to boot.
        容器啟動時 pip install 已移除：該套件不再是相依，且 uv venv 不含 pip。
        """
        command = _services(PROD)["mcp_server"].get("command", "")
        assert "pip install" not in command, f"unexpected pip install in: {command!r}"

    def test_redis_persists(self):
        """Redis holds the Celery result backend and the report queues."""
        volumes = _services(PROD)["redis"].get("volumes") or []
        assert any("advisor_redis_data" in str(v) for v in volumes), (
            "advisor_redis_data was declared but not mounted, so every restart "
            "dropped the queues and the sentinel buffer"
        )

    def test_config_is_bind_mounted_where_the_app_reads_it(self):
        """
        config/ carries the settings registry — the low-code surface. Baked into
        the image only, editing settings_schema.yaml needed a rebuild, which
        defeats a file-driven registry.
        config/ 是低程式碼設定面；只烤進映像時編輯 YAML 需重建才生效。
        """
        svc = _services(PROD)
        for name in ("mcp_server", "worker", "celery_beat"):
            volumes = [str(v) for v in (svc[name].get("volumes") or [])]
            assert any(v.startswith("./config:") for v in volumes), (
                f"{name} does not bind-mount ./config, so schema edits need an image rebuild"
            )


class TestDevCompose:

    def test_observability_stamps_survive(self):
        """
        The six `profiles: [observability]` overrides for the included SigNoz
        services were deleted once by a range edit, silently restoring ~4-6GB of
        RAM to the default boot.
        這六個 profile 覆寫曾被範圍刪除誤刪，讓 SigNoz 靜默回到預設啟動。
        """
        svc = _services(DEV)
        stamped = [n for n, cfg in svc.items() if (cfg or {}).get("profiles") == ["observability"]]
        assert len(stamped) >= 6, (
            f"expected the SigNoz services to carry the observability profile, found {stamped}"
        )

    def test_config_is_bind_mounted(self):
        svc = _services(DEV)
        mounted = [
            n for n, cfg in svc.items()
            if any(str(v).startswith("./config:") for v in ((cfg or {}).get("volumes") or []))
        ]
        assert mounted, "no dev service bind-mounts ./config"


class TestNginx:

    def test_upstreams_resolve_per_request(self):
        """
        Static `upstream` blocks resolve once at startup and cache the IP, so a
        recreated API container left the whole dashboard 502 until nginx was
        restarted by hand — three times across these milestones. A variable in
        proxy_pass forces per-request resolution.
        靜態 upstream 只在啟動時解析並永久快取 IP，API 重建後整站 502 直到手動
        重啟 nginx（已發生三次）。proxy_pass 用變數可每次請求重新解析。
        """
        conf = Path("infra/nginx/nginx.conf").read_text()
        assert "resolver 127.0.0.11" in conf, "Docker's embedded DNS resolver must be configured"
        assert "proxy_pass http://$" in conf, "proxy_pass must use a variable to re-resolve"
        # No static upstream target may remain.
        import re
        static = re.findall(r"proxy_pass http://(?!\$)[^;]+;", conf)
        assert not static, f"static proxy_pass targets still present: {static}"

    def test_webhook_only_vhost_exists(self):
        conf = Path("infra/nginx/nginx.conf").read_text()
        assert "listen 8080;" in conf, "the webhook-only tunnel vhost is missing"
        # Within that vhost, everything unmatched must 404.
        tail = conf[conf.index("listen 8080;"):]
        assert "return 404;" in tail, "the tunnel vhost must 404 unmatched paths"
