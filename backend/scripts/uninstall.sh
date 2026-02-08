#!/usr/bin/env bash
set -euo pipefail

note() { echo "[birdshome] $*"; }
die() { echo "[birdshome] ERROR: $*" >&2; exit 1; }

INSTALL_DIR="${INSTALL_DIR:-/opt/birdshome}"
APP_USER="${APP_USER:-birdshome}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

STATIC_REL="backend/app/static"
DB_REL="backend/birdshome.db"
ENV_REL="backend/.env"

# Welche Verzeichnisse im static-Ordner bleiben sollen (Videos/Bilder).
KEEP_DIRS=("videos" "photos" "images" "timelapses" "media" "timelapse_video" "timelapse_screens" "photos_with_birds" "photos_without_birds" "videos_with_birds" "videos_without_birds")

require_root() {
  [[ "${EUID}" -eq 0 ]] || die "Bitte als root ausführen (sudo)."
}

have_whiptail() {
  command -v whiptail >/dev/null 2>&1
}

get_env_value() {
  local key="$1" file="$2"
  python3 - "$key" "$file" <<'PY'
import sys
key=sys.argv[1]
file=sys.argv[2]
try:
    with open(file,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k,v=line.split('=',1)
            if k.strip()==key:
                val=v.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val=val[1:-1]
                print(val)
                raise SystemExit(0)
except FileNotFoundError:
    pass
raise SystemExit(1)
PY
}

confirm() {
  local title="$1" msg="$2"
  if have_whiptail; then
    whiptail --title "$title" --yesno "$msg" 18 74
    return $?
  fi
  echo
  echo "${title}"
  echo "${msg}"
  echo
  read -r -p "Tippe 'yes' zum Fortfahren: " ans
  [[ "${ans}" == "yes" ]]
}

ask_delete_db() {
  local title msg
  title="Birdshome Deinstallation"
  msg="Soll die Datenbank gelöscht werden?\n\nJa: birdshome.db wird entfernt.\nNein: DB bleibt erhalten, aber der Admin-Nutzer wird gelöscht."
  if have_whiptail; then
    whiptail --title "$title" --yesno "$msg" 16 74
    return $?
  fi
  echo
  echo "$msg"
  read -r -p "Datenbank löschen? (y/N): " ans
  [[ "${ans}" == "y" || "${ans}" == "Y" ]]
}

stop_disable_services() {
  note "Stoppe/Deaktiviere services..."
  local units
  units=()
  # Services aus dem Projekt-Repository (backend/scripts/systemd) ableiten
  for unit_src in "${SCRIPT_DIR}/systemd/"*.service; do
    [[ -f "${unit_src}" ]] || continue
    units+=("$(basename "${unit_src}")")
  done
  if [[ "${#units[@]}" -eq 0 ]]; then
    units=(birdshome.service birdshome-jobs.service)
  fi
  for u in "${units[@]}"; do
    systemctl stop "$u" >/dev/null 2>&1 || true
    systemctl disable "$u" >/dev/null 2>&1 || true
    systemctl reset-failed "$u" >/dev/null 2>&1 || true
  done

  # Entferne auch eventuelle zusätzliche birdshome*.service units.
  while read -r unit_file; do
    rm -f "/etc/systemd/system/${unit_file}" "/lib/systemd/system/${unit_file}" "/usr/lib/systemd/system/${unit_file}" || true
  done < <(systemctl list-unit-files "birdshome*.service" --no-legend 2>/dev/null | awk '{print $1}' || true)

  systemctl daemon-reload >/dev/null 2>&1 || true
}

disable_nginx_site() {
  note "Deaktiviere nginx site..."
  rm -f /etc/nginx/sites-enabled/birdshome /etc/nginx/sites-available/birdshome || true

  # Wenn default existiert und keine andere Site enabled ist, default wieder aktivieren.
  if [[ -f /etc/nginx/sites-available/default && ! -e /etc/nginx/sites-enabled/default ]]; then
    ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default || true
  fi

  if command -v nginx >/dev/null 2>&1; then
    nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
  fi
}

remove_tls_artifacts() {
  note "Entferne lokale TLS Artefakte (self-signed)"
  rm -rf /etc/ssl/birdshome || true
  rm -rf /var/www/certbot || true
}

preserve_static_media() {
  local static_dir="$1" tmp="$2"
  mkdir -p "$tmp"
  if [[ ! -d "$static_dir" ]]; then
    return 0
  fi

  note "Sichere Medien aus ${static_dir}..."
  for d in "${KEEP_DIRS[@]}"; do
    if [[ -d "$static_dir/$d" ]]; then
      mkdir -p "$tmp/$d"
      rsync -a "$static_dir/$d/" "$tmp/$d/"
    fi
  done
}

restore_static_media() {
  local static_dir="$1" tmp="$2"
  note "Stelle Medien wieder her nach ${static_dir}..."
  mkdir -p "$static_dir"
  for d in "${KEEP_DIRS[@]}"; do
    if [[ -d "$tmp/$d" ]]; then
      mkdir -p "$static_dir/$d"
      rsync -a "$tmp/$d/" "$static_dir/$d/"
    fi
  done

  if id -u "$APP_USER" >/dev/null 2>&1; then
    chown -R "$APP_USER:$APP_USER" "$static_dir" || true
  fi
}

delete_admin_from_db() {
  local db_file="$1" env_file="$2"
  [[ -f "$db_file" ]] || return 0

  local username
  username="$(get_env_value ADMIN_USERNAME "$env_file" 2>/dev/null || true)"
  [[ -z "$username" ]] && username="admin"

  note "Entferne Admin-Nutzer aus DB (username=${username})..."
  # Best-effort: falls Schema abweicht, ignorieren.
  sqlite3 "$db_file" <<SQL >/dev/null 2>&1 || true
DELETE FROM users WHERE username = '$username';
DELETE FROM users WHERE is_admin = 1;
SQL
}

main() {
  require_root

  local title msg
  title="Birdshome Deinstallation"
  msg="Birdshome wird deinstalliert.\n\nEntfernt:\n- systemd services (birdshome*)\n- nginx Site-Konfiguration (birdshome)\n- Code/Configs unter ${INSTALL_DIR}\n\nErhalten bleiben nur Medien unter:\n${INSTALL_DIR}/${STATIC_REL}/{${KEEP_DIRS[*]}}\n\nFortfahren?"
  confirm "$title" "$msg" || die "Deinstallation abgebrochen."

  local delete_db
  if ask_delete_db; then
    delete_db=1
  else
    delete_db=0
  fi

  stop_disable_services
  disable_nginx_site
  remove_tls_artifacts

  local static_dir db_file env_file tmp
  static_dir="${INSTALL_DIR}/${STATIC_REL}"
  db_file="${INSTALL_DIR}/${DB_REL}"
  env_file="${INSTALL_DIR}/${ENV_REL}"
  tmp="$(mktemp -d /tmp/birdshome-uninstall.XXXXXX)"

  preserve_static_media "$static_dir" "$tmp"

  if [[ "$delete_db" -eq 1 ]]; then
    note "Datenbank wird gelöscht: ${db_file}"
    rm -f "$db_file" || true
  else
    delete_admin_from_db "$db_file" "$env_file"
  fi

  note "Entferne ${INSTALL_DIR} (außer Medien werden danach wiederhergestellt)..."
  rm -rf "$INSTALL_DIR" || true

  # Nur das static Medienverzeichnis wieder anlegen.
  restore_static_media "$static_dir" "$tmp"

  rm -rf "$tmp" || true

  note "Deinstallation abgeschlossen."
}

main "$@"
