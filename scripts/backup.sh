#!/usr/bin/env bash
# 生产备份脚本：SQLite 原子备份 + uploads + 配置
# 用法: sudo ./scripts/backup.sh   (建议加到 crontab 每小时一次)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/chain}"
KEEP_DAYS="${KEEP_DAYS:-7}"
CHAIN_ROOT="${CHAIN_ROOT:-/opt/chain}"
TS="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

DB="${CHAIN_ROOT}/backend/app/storage/db/chain.sqlite3"
if [ -f "$DB" ]; then
  command -v sqlite3 >/dev/null 2>&1 || { echo "sqlite3 not installed, skipping sqlite backup"; exit 1; }
  sqlite3 "$DB" ".backup $BACKUP_DIR/chain-$TS.sqlite3"
  gzip -9 "$BACKUP_DIR/chain-$TS.sqlite3"
  echo "[+] DB -> $BACKUP_DIR/chain-$TS.sqlite3.gz"
else
  echo "[!] DB not found: $DB, skipping sqlite backup"
fi

# uploads 目录
if [ -d "${CHAIN_ROOT}/backend/app/storage/uploads" ]; then
  tar -czf "$BACKUP_DIR/uploads-$TS.tar.gz" -C "${CHAIN_ROOT}/backend/app/storage" uploads
  echo "[+] uploads -> $BACKUP_DIR/uploads-$TS.tar.gz"
fi

# 关键配置（注意 .env 含密钥，需加密存储或限制 600）
tar -czf "$BACKUP_DIR/config-$TS.tar.gz" \
  "${CHAIN_ROOT}/backend/.env" \
  /etc/nginx/sites-available/chain 2>/dev/null \
  && echo "[+] config -> $BACKUP_DIR/config-$TS.tar.gz" || echo "[!] some config paths missing"

# 清理过期（保留最近 KEEP_DAYS 天）
find "$BACKUP_DIR" -type f \( -name "*.gz" -o -name "*.sqlite3.gz" \) -mtime +"$KEEP_DAYS" -delete

# 权限
chmod 600 "$BACKUP_DIR"/*.gz 2>/dev/null || true

echo "[OK] backup done at $TS"
