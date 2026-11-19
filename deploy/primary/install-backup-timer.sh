#!/usr/bin/env bash
# Installs the nightly backup (systemd timer) on the primary host. Run once as root:
#   sudo ./install-backup-timer.sh age1yourpublickey...
# Only the PUBLIC age key goes on the host; keep the private key offline.
set -euo pipefail
cd "$(dirname "$0")"
recipient="${1:?usage: sudo ./install-backup-timer.sh <age public key>}"
case "$recipient" in age1*) ;; *) echo "Not an age public key (must start with age1)" >&2; exit 1 ;; esac
dir="$(cd ../.. && pwd)"
install -d -m 700 /etc/ezo
umask 077
if [ -f /etc/ezo/backup.env ] && grep -q '^EZO_BACKUP_RCLONE_REMOTE=' /etc/ezo/backup.env; then
  remote="$(grep '^EZO_BACKUP_RCLONE_REMOTE=' /etc/ezo/backup.env)"
else
  remote=""
fi
printf 'EZO_BACKUP_AGE_RECIPIENT=%s\n%s\n' "$recipient" "$remote" > /etc/ezo/backup.env
for unit in ezo-backup.service ezo-backup.timer; do
  sed "s#@EZO_DIR@#${dir}#g" "systemd/${unit}" > "/etc/systemd/system/${unit}"
done
systemctl daemon-reload
systemctl enable --now ezo-backup.timer
systemctl list-timers ezo-backup.timer --no-pager
echo "Nightly backup installed. Test it now: sudo systemctl start ezo-backup.service"
echo "Then prove it restores: ./restore-check.sh backups/<newest>.tar.age  (needs the private key)"
