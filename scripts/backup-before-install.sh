#!/usr/bin/env bash
set -euo pipefail
umask 077
CREATIO_INFRA_ROOT="${1:-$HOME/Desktop/demo/creatio-mssql-lab}"
test -f "$CREATIO_INFRA_ROOT/infra/compose.yaml"
CREATIO_BACKUP_DIR=$(mktemp -d "$CREATIO_INFRA_ROOT/backups/order-calculator-before-install.XXXXXX")
CREATIO_BACKUP_FILE="order-calculator-$(date +%Y%m%dT%H%M%S)-$(basename "$CREATIO_BACKUP_DIR").bak"
export CREATIO_BACKUP_FILE

docker compose -f "$CREATIO_INFRA_ROOT/infra/compose.yaml" exec -T \
  -e CREATIO_BACKUP_FILE mssql /bin/sh -ec '
    case "$CREATIO_BACKUP_FILE" in *[!a-zA-Z0-9._-]*|"") exit 1 ;; esac
    backup_path="/var/opt/mssql/backup/$CREATIO_BACKUP_FILE"
    test ! -e "$backup_path"
    export SQLCMDPASSWORD="$MSSQL_SA_PASSWORD"
    /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -l 10 -t 900 -Q "
      BACKUP DATABASE [creatio_app]
      TO DISK = N'\''$backup_path'\''
      WITH COPY_ONLY, CHECKSUM, COMPRESSION, STATS = 10;
      RESTORE VERIFYONLY FROM DISK = N'\''$backup_path'\'' WITH CHECKSUM;
    "
  '

CREATIO_SQL_CONTAINER=$(docker compose -f "$CREATIO_INFRA_ROOT/infra/compose.yaml" ps -q mssql)
test -n "$CREATIO_SQL_CONTAINER"
docker cp "$CREATIO_SQL_CONTAINER:/var/opt/mssql/backup/$CREATIO_BACKUP_FILE" \
  "$CREATIO_BACKUP_DIR/creatio_app.bak"
chmod 600 "$CREATIO_BACKUP_DIR/creatio_app.bak"
(
  cd "$CREATIO_BACKUP_DIR"
  sha256sum creatio_app.bak > SHA256SUMS
  sha256sum --check SHA256SUMS
)
printf 'OK: SQL backup verified and copied to %s\n' "$CREATIO_BACKUP_DIR"
