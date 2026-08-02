"""product_events: opt-in telemetry (Loop 3, B-P3.2)

2026-07-14: no product analytics exist anywhere in the codebase — there's
no way to know which features get used, which loops actually engage
users, or where to invest next. This table is the sink; writes are
gated by a per-user `telemetry_enabled` setting that defaults to FALSE
for self-host (privacy-first) and would default TRUE for the future
cloud offering (BILLING_MODE=cloud, per the open-core roadmap). Payloads
are feature-name + minimal props only — never financial data.

2026-07-14：目前完全沒有任何產品遙測——無法得知哪些功能被使用、哪個迴圈
真正帶動用戶參與、下一步該投資哪裡。此表是接收端；寫入受 per-user
`telemetry_enabled` 設定閘控，self-host 預設關閉（隱私優先）。payload 只
存功能名稱與最小屬性，絕不含財務資料。

Revision ID: 017_product_events
Revises: 016_remediation_log
Create Date: 2026-07-14
"""
from alembic import op

revision = "017_product_events"
down_revision = "016_remediation_log"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS product_events (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            event TEXT NOT NULL,
            props JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_product_events_lookup
        ON product_events (event, created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS product_events;")
