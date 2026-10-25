#!/bin/bash
# Shared helpers for database backups. Sourced by scripts/backup_db.sh (nightly) and start.sh (pre-deploy).
# 資料庫備份共用函式；由 scripts/backup_db.sh（夜間）與 start.sh（部署前）source。
#
# Dumps are plain SQL piped through gzip (`*.sql.gz`), so restore stays `gzip -cd <file> | psql`.
# 備份是純 SQL 經 gzip 壓縮（`*.sql.gz`），還原仍是 `gzip -cd <file> | psql`。
#
# Written for macOS bash 3.2: no mapfile, no associative arrays. / 相容 macOS bash 3.2。

# verify_sql_gz <file>: exit 0 only if <file> is a valid gzip stream whose SQL ends with pg_dump's completion trailer.
# A non-empty size proves nothing here: gzip of an empty input is still about 20 bytes.
# 只有 gzip 完整且 SQL 結尾有 pg_dump 完成標記才回 0。檔案非空不代表什麼：空輸入壓縮後也有約 20 位元組。
verify_sql_gz() {
    local f="$1"
    [ -s "$f" ] || return 1
    gzip -t "$f" 2>/dev/null || return 1
    gzip -cd "$f" 2>/dev/null | tail -n 5 | grep -q "PostgreSQL database dump complete"
}

# prune_deploy_backups <dir> <keep>: keep the newest <keep> pre-deploy backup groups, delete the rest whole.
# A group is everything `./start.sh backup` writes for one timestamp: db-<ts>.sql[.gz], config-<ts>.tar.gz,
# env-<ts>.bak, manifest-<ts>.json. The manifest is written last, so only complete groups are counted; ordering is by
# the YYYYMMDD-HHMMSS in the name, not by mtime. Milestone dumps (pre-m*), nightly dumps (db_backup_*) and anything
# without a manifest are never touched. <keep> that is not a positive integer disables pruning (never deletes all).
# 保留最近 <keep> 組部署前備份，其餘整組刪除。一組＝同一時戳的 db／config／env／manifest。只以 manifest 計組
# （manifest 最後才寫，不完整的組不算），以檔名時戳排序而非 mtime。里程碑備份（pre-m*）、夜間備份（db_backup_*）、
# 沒有 manifest 的檔一律不碰。<keep> 不是正整數就不清理（絕不全刪）。
prune_deploy_backups() {
    local dir="$1" keep="$2"
    case "$keep" in
        ''|*[!0-9]*) echo "  · Backup retention disabled (DEPLOY_BACKUP_KEEP='${keep}' is not a positive integer)."; return 0 ;;
    esac
    [ "$keep" -ge 1 ] || { echo "  · Backup retention disabled (DEPLOY_BACKUP_KEEP=0)."; return 0; }

    local ts n=0 removed=0
    # Newest first; the name pattern is fixed-width so a reverse lexical sort is chronological.
    # 新到舊；檔名定寬，字典序倒排即時間倒序。
    for ts in $(ls -1 "$dir" 2>/dev/null \
                | grep -E '^manifest-[0-9]{8}-[0-9]{6}\.json$' \
                | sed -e 's/^manifest-//' -e 's/\.json$//' \
                | sort -r); do
        n=$((n + 1))
        [ "$n" -le "$keep" ] && continue
        rm -f "$dir/db-${ts}.sql" "$dir/db-${ts}.sql.gz" "$dir/config-${ts}.tar.gz" \
              "$dir/env-${ts}.bak" "$dir/manifest-${ts}.json"
        removed=$((removed + 1))
        echo "  · Pruned old pre-deploy backup ${ts}"
    done
    echo "  ✓ Kept newest ${keep} pre-deploy backup group(s); pruned ${removed}."
}
