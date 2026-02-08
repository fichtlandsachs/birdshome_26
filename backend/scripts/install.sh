#!/usr/bin/env bash
set -euo pipefail

note() { echo "[birdshome] $*"; }
die() { echo "[birdshome] ERROR: $*" >&2; exit 1; }

# Default values (can be overridden via environment or command-line)
INSTALL_DIR="${INSTALL_DIR:-/opt/birdshome}"
APP_USER="${APP_USER:-birdshome}"
APP_GROUP="${APP_USER}"
NODE_MAJOR="${NODE_MAJOR:-24}"
USE_NODESOURCE="${USE_NODESOURCE:-1}"

# TLS/HTTPS Configuration
TLS_MODE="${TLS_MODE:-}"                       # letsencrypt|selfsigned|none
BIRDSHOME_DOMAIN="${BIRDSHOME_DOMAIN:-}"       # primary hostname / CN
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"
LETSENCRYPT_STAGING="${LETSENCRYPT_STAGING:-0}"
TLS_SELF_SIGNED_SANS="${TLS_SELF_SIGNED_SANS:-}"  # comma-separated DNS/IP SANs
TLS_SELF_SIGNED_DAYS="${TLS_SELF_SIGNED_DAYS:-825}"

# Admin credentials
ADMIN_USERNAME="${ADMIN_USERNAME:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"

# Audio device
AUDIO_SOURCE="${AUDIO_SOURCE:-}"

# Firewall
ENABLE_UFW="${ENABLE_UFW:-1}"

# VPN / Remote Access
ENABLE_TAILSCALE="${ENABLE_TAILSCALE:-1}"
TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}"

# SSH Key Setup
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNINSTALL_SCRIPT="${SCRIPT_DIR}/uninstall.sh"
SOURCE_ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"   # repository root (frontend + backend)

# Track if we're in silent mode (all params provided)
SILENT_MODE=0

# Track if reboot is needed (e.g., for I2C activation)
REBOOT_REQUIRED=0

require_root() {
  [[ "${EUID}" -eq 0 ]] || die "Bitte als root ausführen (sudo)."
}

have_whiptail() {
  command -v whiptail >/dev/null 2>&1
}

is_interactive() {
  [[ -t 0 && -t 1 ]]
}

# Parse command-line arguments
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --user=*)
        APP_USER="${1#*=}"
        shift
        ;;
      --tls-mode=*)
        TLS_MODE="${1#*=}"
        shift
        ;;
      --domain=*)
        BIRDSHOME_DOMAIN="${1#*=}"
        shift
        ;;
      --email=*)
        LETSENCRYPT_EMAIL="${1#*=}"
        shift
        ;;
      --sans=*)
        TLS_SELF_SIGNED_SANS="${1#*=}"
        shift
        ;;
      --admin-user=*)
        ADMIN_USERNAME="${1#*=}"
        shift
        ;;
      --admin-password=*)
        ADMIN_PASSWORD="${1#*=}"
        shift
        ;;
      --audio=*)
        AUDIO_SOURCE="${1#*=}"
        shift
        ;;
      --enable-ufw=*)
        ENABLE_UFW="${1#*=}"
        shift
        ;;
      --enable-tailscale=*)
        ENABLE_TAILSCALE="${1#*=}"
        shift
        ;;
      --tailscale-key=*)
        TAILSCALE_AUTH_KEY="${1#*=}"
        shift
        ;;
      --ssh-key=*)
        SSH_PUBLIC_KEY="${1#*=}"
        shift
        ;;
      --install-dir=*)
        INSTALL_DIR="${1#*=}"
        shift
        ;;
      --silent)
        SILENT_MODE=1
        shift
        ;;
      install|--install)
        shift
        ;;
      uninstall|remove|--uninstall|--remove)
        require_root
        exec "${UNINSTALL_SCRIPT}"
        ;;
      help|-h|--help)
        usage
        exit 0
        ;;
      *)
        note "Unbekannter Parameter: $1"
        shift
        ;;
    esac
  done
}

usage() {
  cat <<EOF
Birdshome Installation Script

Usage:
  sudo ./backend/scripts/install.sh [OPTIONS]

Options:
  --user=USER                System user for running services (default: birdshome)
  --install-dir=DIR          Installation directory (default: /opt/birdshome)
  --tls-mode=MODE            TLS mode: letsencrypt|selfsigned|none (default: interactive)
  --domain=DOMAIN            Domain name for HTTPS
  --email=EMAIL              Email for Let's Encrypt notifications
  --sans=SANS                Comma-separated SANs for self-signed cert
  --admin-user=USER          Admin username (default: admin)
  --admin-password=PASS      Admin password (default: generated)
  --audio=SOURCE             Audio source (e.g., "-f alsa -i hw:0,0" or "none")
  --enable-ufw=0|1           Enable UFW firewall (default: 1)
  --enable-tailscale=0|1     Enable Tailscale VPN for remote access (default: 1)
  --tailscale-key=KEY        Tailscale auth key for auto-connect (optional)
  --ssh-key=KEY              SSH public key for key-based authentication (optional)
  --silent                   Non-interactive mode (requires all params)

Examples:
  # Interactive installation with dialogs
  sudo ./backend/scripts/install.sh

  # Silent installation with Let's Encrypt
  sudo ./backend/scripts/install.sh \\
    --tls-mode=letsencrypt \\
    --domain=birdshome.example.com \\
    --email=admin@example.com \\
    --admin-user=admin \\
    --admin-password=secret123 \\
    --audio=none \\
    --silent

  # Silent installation with self-signed certificate
  sudo ./backend/scripts/install.sh \\
    --tls-mode=selfsigned \\
    --domain=birdshome.local \\
    --sans=birdshome.local,localhost,127.0.0.1 \\
    --admin-user=admin \\
    --admin-password=secret123 \\
    --silent

  # Silent HTTP-only installation
  sudo ./backend/scripts/install.sh \\
    --tls-mode=none \\
    --domain=192.168.1.100 \\
    --admin-password=secret123 \\
    --silent

  # Installation with Tailscale VPN and SSH Key for remote access
  sudo ./backend/scripts/install.sh \\
    --tls-mode=selfsigned \\
    --domain=birdshome.local \\
    --admin-password=secret123 \\
    --enable-tailscale=1 \\
    --tailscale-key=tskey-auth-xxxxx-xxxxx \\
    --ssh-key="ssh-ed25519 AAAAC3NzaC1... user@hostname" \\
    --silent

  # Uninstall
  sudo ./backend/scripts/install.sh uninstall
EOF
}

# Collect missing parameters interactively
collect_parameters() {
  note "Sammle Installationsparameter..."

  # Load existing values from .env if available
  local env_file="${INSTALL_DIR}/backend/.env"
  if [[ -f "${env_file}" ]]; then
    [[ -z "${ADMIN_USERNAME}" ]] && ADMIN_USERNAME="$(get_env_value ADMIN_USERNAME "${env_file}" 2>/dev/null || true)"
    [[ -z "${BIRDSHOME_DOMAIN}" ]] && BIRDSHOME_DOMAIN="$(get_env_value PUBLIC_DOMAIN "${env_file}" 2>/dev/null || true)"
    [[ -z "${LETSENCRYPT_EMAIL}" ]] && LETSENCRYPT_EMAIL="$(get_env_value LETSENCRYPT_EMAIL "${env_file}" 2>/dev/null || true)"
    [[ -z "${TLS_MODE}" ]] && TLS_MODE="$(get_env_value TLS_MODE "${env_file}" 2>/dev/null || true)"
    [[ -z "${TLS_SELF_SIGNED_SANS}" ]] && TLS_SELF_SIGNED_SANS="$(get_env_value TLS_SELF_SIGNED_SANS "${env_file}" 2>/dev/null || true)"
  fi

  # Set defaults
  [[ -z "${ADMIN_USERNAME}" ]] && ADMIN_USERNAME="admin"
  [[ -z "${TLS_MODE}" ]] && TLS_MODE="none"

  # If not interactive or silent mode, skip dialogs
  if [[ "${SILENT_MODE}" -eq 1 ]] || ! is_interactive || ! have_whiptail; then
    validate_parameters
    return 0
  fi

  # Interactive parameter collection
  collect_user_param
  collect_tls_params
  collect_admin_params
  collect_audio_param

  validate_parameters
}

collect_user_param() {
  local user
  user=$(whiptail --title "Birdshome Setup" --inputbox \
    "System-Benutzer für die Ausführung:" 10 72 "${APP_USER}" 3>&1 1>&2 2>&3) || die "Installation abgebrochen."
  user="$(echo "${user}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "${user}" ]] && APP_USER="${user}"
}

collect_tls_params() {
  # TLS Mode Selection
  local default mode
  default="${TLS_MODE}"
  [[ -z "${default}" ]] && default="none"

  local on_le=OFF on_ss=OFF on_none=OFF
  case "${default}" in
    letsencrypt) on_le=ON ;;
    selfsigned)  on_ss=ON ;;
    *)           on_none=ON ;;
  esac

  mode=$(whiptail --title "Birdshome TLS" --radiolist \
    "Zertifikatstyp oder Verbindungsmodus wählen:\n\n- Let's Encrypt: öffentlich (DNS/Port 80 erforderlich)\n- Self-signed: lokal verschlüsselt (Zertifikatswarnung)\n- Kein TLS (HTTP): unverschlüsselt (nur für lokales Netz)" \
    20 78 3 \
    "letsencrypt" "Let's Encrypt (HTTPS)" ${on_le} \
    "selfsigned"  "Self-signed (HTTPS)" ${on_ss} \
    "none"        "Kein TLS (nur HTTP)" ${on_none} \
    3>&1 1>&2 2>&3) || die "Installation abgebrochen."

  TLS_MODE="${mode}"

  # Mode-specific parameters
  case "${TLS_MODE}" in
    letsencrypt)
      collect_letsencrypt_params
      ;;
    selfsigned)
      collect_selfsigned_params
      ;;
    none)
      collect_domain_param "HTTP"
      ;;
  esac
}

collect_letsencrypt_params() {
  local domain email
  domain="${BIRDSHOME_DOMAIN}"
  email="${LETSENCRYPT_EMAIL}"

  [[ -z "${domain}" ]] && domain="example.com"
  [[ -z "${email}" ]] && email="admin@example.com"

  while true; do
    domain="$(whiptail --title "Birdshome HTTPS" --inputbox \
      "Domain (FQDN) für HTTPS (DNS muss auf diesen Server zeigen):" 11 78 "${domain}" \
      3>&1 1>&2 2>&3)" || die "Installation abgebrochen."
    domain="$(echo "${domain}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    if [[ -z "${domain}" || "${domain}" == "example.com" ]]; then
      whiptail --title "Birdshome HTTPS" --msgbox \
        "Ein gültiger Domainname ist erforderlich (z.B. birdshome.de)." 10 60
      continue
    fi
    break
  done

  while true; do
    email="$(whiptail --title "Birdshome HTTPS" --inputbox \
      "E-Mail für Let's Encrypt (Ablauf-/Sicherheitsinfos):" 11 78 "${email}" \
      3>&1 1>&2 2>&3)" || die "Installation abgebrochen."
    email="$(echo "${email}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    if [[ -z "${email}" || "${email}" == "admin@example.com" ]]; then
      whiptail --title "Birdshome HTTPS" --msgbox "Eine gültige E-Mail ist erforderlich." 10 60
      continue
    fi
    break
  done

  BIRDSHOME_DOMAIN="${domain}"
  LETSENCRYPT_EMAIL="${email}"
}

collect_selfsigned_params() {
  local domain sans
  domain="${BIRDSHOME_DOMAIN}"
  sans="${TLS_SELF_SIGNED_SANS}"

  [[ -z "${domain}" ]] && domain="birdshome.local"
  [[ -z "${sans}" ]] && sans="${domain},localhost,127.0.0.1"

  domain=$(whiptail --title "Birdshome TLS" --inputbox \
    "Hostname (CN) für das self-signed Zertifikat:" 11 78 "${domain}" \
    3>&1 1>&2 2>&3) || die "Installation abgebrochen."
  domain="$(echo "${domain}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  sans=$(whiptail --title "Birdshome TLS" --inputbox \
    "SubjectAltNames (DNS/IP), komma-separiert:\nBeispiel: birdshome.local,localhost,127.0.0.1" \
    12 78 "${sans}" 3>&1 1>&2 2>&3) || die "Installation abgebrochen."
  sans="$(echo "${sans}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  [[ -z "${domain}" ]] && die "Hostname ist erforderlich."
  [[ -z "${sans}" ]] && sans="${domain}"

  BIRDSHOME_DOMAIN="${domain}"
  TLS_SELF_SIGNED_SANS="${sans}"
}

collect_domain_param() {
  local mode_label="$1"
  local domain
  domain="${BIRDSHOME_DOMAIN}"
  [[ -z "${domain}" ]] && domain="birdshome.local"

  domain=$(whiptail --title "Birdshome ${mode_label}" --inputbox \
    "Hostname oder IP-Adresse für den Zugriff:" 10 72 "${domain}" \
    3>&1 1>&2 2>&3) || die "Installation abgebrochen."
  domain="$(echo "${domain}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  BIRDSHOME_DOMAIN="${domain}"
}

collect_admin_params() {
  local username pw1 pw2
  username="${ADMIN_USERNAME}"
  [[ -z "${username}" ]] && username="admin"

  username="$(whiptail --title "Birdshome Setup" --inputbox \
    "Admin Benutzername:" 10 72 "${username}" 3>&1 1>&2 2>&3)" || die "Installation abgebrochen."
  username="$(echo "${username}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -z "${username}" ]] && username="admin"

  ADMIN_USERNAME="${username}"

  # Skip password dialog if already set
  [[ -n "${ADMIN_PASSWORD}" ]] && return 0

  # Password input loop
  while true; do
    pw1="$(whiptail --title "Birdshome Setup" --passwordbox \
      "Admin Passwort festlegen (Pflicht):" 10 72 3>&1 1>&2 2>&3)" || die "Installation abgebrochen."
    pw1="$(echo "${pw1}" | tr -d '\r\n')"

    if [[ -z "${pw1}" ]]; then
      whiptail --title "Birdshome Setup" --msgbox "Das Passwort darf nicht leer sein!" 10 60
      continue
    fi

    pw2="$(whiptail --title "Birdshome Setup" --passwordbox \
      "Passwort erneut eingeben:" 10 72 3>&1 1>&2 2>&3)" || die "Installation abgebrochen."
    pw2="$(echo "${pw2}" | tr -d '\r\n')"

    if [[ "${pw1}" != "${pw2}" ]]; then
      whiptail --title "Birdshome Setup" --msgbox \
        "Passwörter stimmen nicht überein. Bitte erneut versuchen." 10 60
    else
      break
    fi
  done

  ADMIN_PASSWORD="${pw1}"
}

collect_audio_param() {
  # Skip if already set
  [[ -n "${AUDIO_SOURCE}" ]] && return 0

  note "Suche nach Audio-Hardware..."

  local devices=()
  while IFS= read -r line; do
    local card_id device_id name
    card_id=$(echo "$line" | cut -d' ' -f2 | tr -d ':')
    device_id=$(echo "$line" | cut -d' ' -f5 | tr -d ':')
    name=$(echo "$line" | cut -d'[' -f2 | cut -d']' -f1)
    devices+=("hw:${card_id},${device_id}" "$name")
  done < <(arecord -l 2>/dev/null | grep '^card' || true)

  devices+=("none" "Kein Mikrofon (Stille senden)")

  local choice
  if [[ "${#devices[@]}" -gt 2 ]]; then
    choice=$(whiptail --title "Birdshome Audio Setup" --menu \
      "Wähle das Mikrofon für den Stream:" 15 78 5 \
      "${devices[@]}" 3>&1 1>&2 2>&3) || choice="none"
  else
    choice="none"
  fi

  if [[ "$choice" == "none" ]]; then
    AUDIO_SOURCE="-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000"
  else
    AUDIO_SOURCE="-f alsa -i ${choice}"
  fi
}

validate_parameters() {
  note "Validiere Parameter..."

  # Validate TLS mode
  case "${TLS_MODE}" in
    letsencrypt)
      [[ -z "${BIRDSHOME_DOMAIN}" ]] && die "BIRDSHOME_DOMAIN ist erforderlich für Let's Encrypt."
      [[ -z "${LETSENCRYPT_EMAIL}" ]] && die "LETSENCRYPT_EMAIL ist erforderlich für Let's Encrypt."
      ;;
    selfsigned)
      [[ -z "${BIRDSHOME_DOMAIN}" ]] && die "BIRDSHOME_DOMAIN ist erforderlich für self-signed."
      [[ -z "${TLS_SELF_SIGNED_SANS}" ]] && TLS_SELF_SIGNED_SANS="${BIRDSHOME_DOMAIN},localhost,127.0.0.1"
      ;;
    none)
      [[ -z "${BIRDSHOME_DOMAIN}" ]] && BIRDSHOME_DOMAIN="birdshome.local"
      ;;
    *)
      die "Ungültiger TLS_MODE: ${TLS_MODE}. Muss sein: letsencrypt, selfsigned oder none."
      ;;
  esac

  # Validate admin
  [[ -z "${ADMIN_USERNAME}" ]] && ADMIN_USERNAME="admin"

  # Generate password if not provided
  if [[ -z "${ADMIN_PASSWORD}" ]]; then
    ADMIN_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)"
    note "Admin-Passwort wurde generiert."
  fi

  # Audio default
  if [[ -z "${AUDIO_SOURCE}" ]]; then
    AUDIO_SOURCE="-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000"
  fi

  note "Parameter validiert und vollständig."
}

print_configuration() {
  note "=== Installationskonfiguration ==="
  note "Installationsverzeichnis: ${INSTALL_DIR}"
  note "Benutzer: ${APP_USER}"
  note "TLS-Modus: ${TLS_MODE}"
  note "Domain: ${BIRDSHOME_DOMAIN}"
  [[ "${TLS_MODE}" == "letsencrypt" ]] && note "Let's Encrypt Email: ${LETSENCRYPT_EMAIL}"
  [[ "${TLS_MODE}" == "selfsigned" ]] && note "Self-signed SANs: ${TLS_SELF_SIGNED_SANS}"
  note "Admin-Benutzer: ${ADMIN_USERNAME}"
  note "Audio: ${AUDIO_SOURCE}"
  note "UFW Firewall: $([ "${ENABLE_UFW}" -eq 1 ] && echo "aktiviert" || echo "deaktiviert")"
  note "==================================="
}

install_os_packages() {
  command -v apt-get >/dev/null 2>&1 || die "apt-get nicht gefunden. Dieses Script erwartet Debian/Ubuntu/Raspberry Pi OS."
  export DEBIAN_FRONTEND=noninteractive
  note "Installiere OS Pakete (Python, nginx, ffmpeg, sqlite3, Build-Tools)..."
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg git \
    build-essential python3 python3-pip python3-venv python3-dev \
    ffmpeg nginx sqlite3 rsync whiptail openssl sudo \
    libssl-dev libffi-dev libjpeg-dev zlib1g-dev rclone i2c-tools alsa-utils

  # Try to install numpy/opencv optimization libraries (optional, may not be available on all systems)
  note "Installiere optionale Optimierungsbibliotheken..."
  for pkg in libopenblas-dev gfortran; do
    apt-get install -y --no-install-recommends "${pkg}" 2>/dev/null || \
      note "  ${pkg} nicht verfügbar (übersprungen)"
  done

  # On Raspberry Pi, also install system OpenCV and numpy libs to speed up pip installation
  if [[ -f /proc/device-tree/model ]] && grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
    #note "Raspberry Pi erkannt - installiere OpenCV/NumPy Systembibliotheken..."
    for pkg in libopencv-dev python3-opencv; do
      apt-get install -y --no-install-recommends "${pkg}" 2>/dev/null || \
        note "  ${pkg} nicht verfügbar (übersprungen)"
    done
  fi
}

ensure_certbot() {
  [[ "${TLS_MODE}" != "letsencrypt" ]] && return 0
  command -v certbot >/dev/null 2>&1 && return 0
  export DEBIAN_FRONTEND=noninteractive
  note "Installiere certbot (Let's Encrypt)..."
  apt-get update
  apt-get install -y --no-install-recommends certbot python3-certbot-nginx
}

ensure_node() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    local v major
    v="$(node -v | sed 's/^v//')"
    major="${v%%.*}"
    if [[ "${major}" =~ ^[0-9]+$ ]] && [[ "${major}" -ge "${NODE_MAJOR}" ]]; then
      note "Node.js ist vorhanden (v${v})."
      return 0
    fi
  fi

  note "Installiere Node.js (LTS) für den Frontend-Build..."
  if [[ "${USE_NODESOURCE}" == "1" ]]; then
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
    apt-get install -y nodejs
  else
    apt-get install -y nodejs npm
  fi
}

run_as_app() {
  sudo -u "${APP_USER}" -H "$@"
}

ensure_user() {
  # Create group if it doesn't exist
  if ! getent group "${APP_GROUP}" >/dev/null; then
    note "Erstelle Gruppe ${APP_GROUP}..."
    groupadd --system "${APP_GROUP}"
  fi

  # Create app user and add to group
  if id -u "${APP_USER}" >/dev/null 2>&1; then
    note "User ${APP_USER} existiert bereits."
    usermod -a -G "${APP_GROUP}" "${APP_USER}"
  else
    note "Erstelle System-User ${APP_USER}..."
    useradd --system --home-dir "${INSTALL_DIR}" --shell /usr/sbin/nologin --create-home -g "${APP_GROUP}" "${APP_USER}"
  fi

  # Add additional users to group
  for extra_user in "pi" "${SUDO_USER:-}"; do
    if [[ -n "${extra_user}" ]] && id -u "${extra_user}" >/dev/null 2>&1; then
      note "Füge Nutzer ${extra_user} der Gruppe ${APP_GROUP} hinzu..."
      usermod -a -G "${APP_GROUP}" "${extra_user}"
    fi
  done

  # Add to video/audio groups for hardware access
  usermod -a -G video "${APP_USER}" 2>/dev/null || true
  usermod -a -G audio "${APP_USER}" 2>/dev/null || true
}

enable_i2c() {
  note "Prüfe I2C Status..."

  # Check if running on Raspberry Pi
  if [[ ! -f /proc/device-tree/model ]] || ! grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
    note "Kein Raspberry Pi erkannt, überspringe I2C-Konfiguration"
    return 0
  fi

  # Check if I2C is already enabled
  if lsmod | grep -q "^i2c_dev"; then
    note "I2C ist bereits aktiviert"
    return 0
  fi

  note "I2C wird aktiviert..."

  # Enable I2C in /boot/config.txt or /boot/firmware/config.txt
  local config_file=""
  if [[ -f /boot/firmware/config.txt ]]; then
    config_file="/boot/firmware/config.txt"
  elif [[ -f /boot/config.txt ]]; then
    config_file="/boot/config.txt"
  else
    note "WARNUNG: config.txt nicht gefunden, I2C kann nicht aktiviert werden"
    return 0
  fi

  note "Aktiviere I2C in ${config_file}..."

  # Track if changes were made
  local i2c_config_changed=0

  # Check if dtparam=i2c_arm is already present
  if grep -q "^dtparam=i2c_arm=on" "${config_file}"; then
    note "I2C bereits in ${config_file} aktiviert"
  elif grep -q "^#dtparam=i2c_arm=on" "${config_file}"; then
    # Uncomment existing line
    sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' "${config_file}"
    note "I2C-Zeile in ${config_file} aktiviert"
    i2c_config_changed=1
  else
    # Add new line
    echo "dtparam=i2c_arm=on" >> "${config_file}"
    note "I2C-Zeile zu ${config_file} hinzugefügt"
    i2c_config_changed=1
  fi

  # Enable i2c-dev module in /etc/modules
  if [[ -f /etc/modules ]]; then
    if ! grep -q "^i2c-dev" /etc/modules; then
      echo "i2c-dev" >> /etc/modules
      note "i2c-dev zu /etc/modules hinzugefügt"
      i2c_config_changed=1
    fi
  fi

  # Load i2c-dev module immediately (may not work without reboot)
  if ! lsmod | grep -q "^i2c_dev"; then
    if modprobe i2c-dev 2>/dev/null; then
      note "i2c-dev Modul wurde geladen"
    else
      note "WARNUNG: Konnte i2c-dev Modul nicht laden (benötigt Neustart)"
      i2c_config_changed=1
    fi
  fi

  # Add user to i2c group if it exists
  if getent group i2c >/dev/null 2>&1; then
    usermod -a -G i2c "${APP_USER}" 2>/dev/null || true
    note "Benutzer ${APP_USER} zur Gruppe i2c hinzugefügt"
  fi

  # Set reboot required flag if changes were made
  if [[ "${i2c_config_changed}" -eq 1 ]]; then
    REBOOT_REQUIRED=1
    note "I2C-Konfiguration wurde geändert - Neustart erforderlich"
  else
    note "I2C-Konfiguration abgeschlossen"
  fi
}

rsync_repo() {
  note "Deploy nach ${INSTALL_DIR}..."
  mkdir -p "${INSTALL_DIR}"

  # Backup data directory if it exists
  local data_backup=""
  if [[ -d "${INSTALL_DIR}/backend/data" ]]; then
    data_backup="$(mktemp -d)"
    note "Sichere data Verzeichnis nach ${data_backup}..."
    rsync -a "${INSTALL_DIR}/backend/data/" "${data_backup}/"
  fi

  # Remove old venv to ensure clean installation
  if [[ -d "${INSTALL_DIR}/backend/.venv" ]]; then
    note "Entferne alte venv für saubere Neuinstallation..."
    rm -rf "${INSTALL_DIR}/backend/.venv"
  fi

  rsync -a --delete \
    --exclude '.git/' \
    --exclude 'frontend/node_modules/' \
    --exclude 'frontend/dist/' \
    --exclude 'backend/.venv/' \
    --exclude 'backend/.env' \
    --exclude 'backend/birdshome.db' \
    --exclude 'backend/app/static/' \
    --exclude 'backend/data/' \
    "${SOURCE_ROOT_DIR}/" "${INSTALL_DIR}/"

  # Restore data directory if it was backed up
  if [[ -n "${data_backup}" && -d "${data_backup}" ]]; then
    note "Stelle data Verzeichnis wieder her..."
    mkdir -p "${INSTALL_DIR}/backend/data"
    rsync -a "${data_backup}/" "${INSTALL_DIR}/backend/data/"
    rm -rf "${data_backup}"
  fi

  chown -R "${APP_USER}:${APP_GROUP}" "${INSTALL_DIR}" || true
  find "${INSTALL_DIR}" -type d -exec chmod 2775 {} +
  find "${INSTALL_DIR}" -type f -exec chmod 664 {} +

  mkdir -p "${INSTALL_DIR}/backend/app/static/hls"
  chown -R "${APP_USER}:${APP_GROUP}" "${INSTALL_DIR}/backend/app/static/hls"
  chmod -R 755 "${INSTALL_DIR}/backend/app/static/hls"
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

set_env_kv() {
  local key="$1" value="$2" file="$3"
  python3 - "$key" "$value" "$file" <<'PY'
import sys,re
key=sys.argv[1]
value=sys.argv[2]
file=sys.argv[3]

safe = re.fullmatch(r"[A-Za-z0-9_./:@+\-]+", value or "")
if safe:
    enc = value
else:
    esc = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    enc = f'"{esc}"'

lines=[]
try:
    with open(file,'r',encoding='utf-8') as f:
        lines=f.read().splitlines()
except FileNotFoundError:
    lines=[]

out=[]
found=False
for line in lines:
    if re.match(r'^\s*'+re.escape(key)+r'\s*=', line):
        out.append(f"{key}={enc}")
        found=True
    else:
        out.append(line)
if not found:
    out.append(f"{key}={enc}")

with open(file,'w',encoding='utf-8') as f:
    f.write("\n".join(out)+"\n")
PY
}

bootstrap_env() {
  local backend_dir env_example env_file
  backend_dir="${INSTALL_DIR}/backend"
  env_example="${backend_dir}/.env.example"
  env_file="${backend_dir}/.env"

  [[ -f "${env_example}" ]] || die "${env_example} nicht gefunden."

  if [[ ! -f "${env_file}" ]]; then
    cp "${env_example}" "${env_file}"
    note "Erstellt: ${env_file} (aus .env.example)"
    set_env_kv FLASK_ENV production "${env_file}"
  else
    note "Bestehende .env gefunden (wird aktualisiert): ${env_file}"
  fi

  # SECRET_KEY
  local secret
  secret="$(get_env_value SECRET_KEY "${env_file}" 2>/dev/null || true)"
  if [[ -z "${secret}" || "${secret}" == "change-me" ]]; then
    secret="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
    set_env_kv SECRET_KEY "${secret}" "${env_file}"
    note "SECRET_KEY generiert"
  fi

  # INTERNAL_TOKEN
  local itoken
  itoken="$(get_env_value INTERNAL_TOKEN "${env_file}" 2>/dev/null || true)"
  if [[ -z "${itoken}" || "${itoken}" == "change-me" ]]; then
    itoken="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
    set_env_kv INTERNAL_TOKEN "${itoken}" "${env_file}"
    note "INTERNAL_TOKEN generiert"
  fi

  # STREAM_UDP_URL
  local udp_url
  udp_url="$(get_env_value STREAM_UDP_URL "${env_file}" 2>/dev/null || true)"
  if [[ -z "${udp_url}" ]]; then
    udp_url="udp://127.0.0.1:5004?pkt_size=1316&reuse=1&overrun_nonfatal=1&fifo_size=5000000"
    set_env_kv STREAM_UDP_URL "${udp_url}" "${env_file}"
  fi

  # Persist collected parameters
  set_env_kv TLS_MODE "${TLS_MODE}" "${env_file}"
  set_env_kv PUBLIC_DOMAIN "${BIRDSHOME_DOMAIN}" "${env_file}"
  set_env_kv ADMIN_USERNAME "${ADMIN_USERNAME}" "${env_file}"
  set_env_kv AUDIO_SOURCE "${AUDIO_SOURCE}" "${env_file}"

  [[ "${TLS_MODE}" == "letsencrypt" ]] && set_env_kv LETSENCRYPT_EMAIL "${LETSENCRYPT_EMAIL}" "${env_file}"
  [[ "${TLS_MODE}" == "selfsigned" ]] && set_env_kv TLS_SELF_SIGNED_SANS "${TLS_SELF_SIGNED_SANS}" "${env_file}"

  # Save admin password temporarily
  echo "${ADMIN_PASSWORD}" > "${backend_dir}/.admin_password_temp"
  chmod 600 "${backend_dir}/.admin_password_temp"

  chown "${APP_USER}:${APP_GROUP}" "${env_file}" || true
  chmod 640 "${env_file}"
}

setup_backend() {
  local backend_dir venv
  backend_dir="${INSTALL_DIR}/backend"
  venv="${backend_dir}/.venv"

  note "Initialisiere Backend (venv + requirements)..."

  # Always remove old venv for clean installation (already done in rsync_repo, but double-check)
  if [[ -d "${venv}" ]]; then
    note "Entferne vorhandenes venv für saubere Neuinstallation..."
    rm -rf "${venv}"
  fi

  # Create fresh venv as app user
  note "Erstelle neues Python venv..."

  # Ensure backend directory has correct ownership before creating venv
  chown -R "${APP_USER}:${APP_GROUP}" "${backend_dir}"

  # Create venv with --copies to avoid symlink issues
  run_as_app python3 -m venv --copies "${venv}"

  # Verify venv was created successfully
  if [[ ! -f "${venv}/bin/pip" ]]; then
    note "Debug: Prüfe venv-Verzeichnis..."
    ls -la "${venv}/bin/" || true
    python3 --version
    python3 -m venv --help || true
    die "Python venv konnte nicht erstellt werden. Pip-Binary fehlt in ${venv}/bin/"
  fi

  # Upgrade pip and install requirements
  note "Aktualisiere pip, setuptools und wheel..."

  # Upgrade pip, setuptools, wheel - newer versions handle metadata preparation faster
  run_as_app "${venv}/bin/python" -m pip install --quiet --upgrade pip setuptools wheel || \
    note "WARNUNG: pip upgrade fehlgeschlagen - verwende vorhandene Version"

  # Verify pip is working before proceeding
  if ! run_as_app "${venv}/bin/python" -m pip --version >/dev/null 2>&1; then
    die "pip ist nicht funktionsfähig. Bitte lösche ${venv} und versuche es erneut."
  fi

  note "pip Version: $(run_as_app ${venv}/bin/python -m pip --version)"

  # Configure piwheels for Raspberry Pi to use precompiled wheels (much faster!)
  if [[ -f /proc/device-tree/model ]] && grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
    note "Raspberry Pi erkannt - aktiviere piwheels für schnellere Installation..."

    # Add piwheels as extra index (this allows pip to find precompiled ARM wheels)
    run_as_app "${venv}/bin/pip" config set global.extra-index-url https://www.piwheels.org/simple

    note "Piwheels aktiviert - numpy und opencv-python werden als vorkompilierte Pakete installiert"
  fi

  # Install requirements
  note "Installiere Python-Pakete aus requirements.txt..."
  note "  (Flask, numpy, opencv-python - dies kann 2-5 Minuten dauern)"

  # Use --prefer-binary to skip building from source when wheels are available
  # Use --only-binary for numpy and opencv-python to force wheel usage (skip metadata preparation)
  # This dramatically speeds up installation by avoiding pyproject.toml processing
  run_as_app "${venv}/bin/python" -m pip install \
    --prefer-binary \
    --only-binary=numpy,opencv-python \
    --upgrade \
    -r "${backend_dir}/requirements.txt" || die "requirements.txt Installation fehlgeschlagen"

  note "Python-Pakete erfolgreich installiert"

  # Create static and media directories
  note "Erstelle Static- und Media-Verzeichnisse..."
  mkdir -p "${backend_dir}/app/static/app" \
    "${backend_dir}/app/static/hls" \
    "${backend_dir}/data/snapshots" \
    "${backend_dir}/data/motion" \
    "${backend_dir}/data/motion_video" \
    "${backend_dir}/data/timelapse_screens" \
    "${backend_dir}/data/timelapse_video"

  chown -R "${APP_USER}:${APP_GROUP}" "${backend_dir}/app/static" "${backend_dir}/data"
  chmod -R 775 "${backend_dir}/app/static/hls"
  chmod -R 775 "${backend_dir}/data"

  # Ensure backend directory is writable for database
  chown -R "${APP_USER}:${APP_GROUP}" "${backend_dir}"
  chmod 775 "${backend_dir}"

  # If database exists, ensure it's writable
  if [[ -f "${backend_dir}/birdshome.db" ]]; then
    chown "${APP_USER}:${APP_GROUP}" "${backend_dir}/birdshome.db"
    chmod 664 "${backend_dir}/birdshome.db"
  fi
}

build_frontend() {
  local frontend_dir backend_dir
  frontend_dir="${INSTALL_DIR}/frontend"
  backend_dir="${INSTALL_DIR}/backend"

  note "Baue Frontend (npm install + build)..."

  # Ensure frontend directory has correct ownership
  chown -R "${APP_USER}:${APP_GROUP}" "${frontend_dir}"

  # Clean all build caches and artifacts for fresh build
  note "Entferne alte Build-Caches..."
  rm -rf "${frontend_dir}/node_modules" \
         "${frontend_dir}/dist" \
         "${frontend_dir}/.vite" \
         "${frontend_dir}/.cache" \
         "${frontend_dir}/.turbo" || true

  # Update npm to latest version
  note "Aktualisiere npm..."
  npm install -g npm@latest || note "npm update übersprungen (nicht kritisch)"

  # Install and build as app user to avoid permission issues
  note "Installiere npm-Pakete (saubere Installation)..."
  run_as_app bash -c "cd '${frontend_dir}' && npm install"

  # Make node_modules binaries executable
  if [[ -d "${frontend_dir}/node_modules/.bin" ]]; then
    chmod -R 755 "${frontend_dir}/node_modules/.bin"
    chown -R "${APP_USER}:${APP_GROUP}" "${frontend_dir}/node_modules"
  fi

  note "Baue Frontend mit Vite..."
  run_as_app bash -c "cd '${frontend_dir}' && npm run build"

  note "Deploy Frontend nach backend/app/static/app..."
  rm -rf "${backend_dir}/app/static/app" || true
  mkdir -p "${backend_dir}/app/static/app"
  rsync -a "${frontend_dir}/dist/" "${backend_dir}/app/static/app/"
  chown -R "${APP_USER}:${APP_GROUP}" "${backend_dir}/app/static/app" || true
}

sync_admin_user_db() {
  local backend_dir venv password_file
  backend_dir="${INSTALL_DIR}/backend"
  venv="${backend_dir}/.venv"
  password_file="${backend_dir}/.admin_password_temp"

  [[ -f "${password_file}" ]] || die "Passwort-Datei ${password_file} nicht gefunden."

  note "Synchronisiere Admin-Nutzer in DB..."

  local password
  password="$(cat "${password_file}")"

  run_as_app bash -c "cd '${backend_dir}' && '${venv}/bin/python' - '${password}'" <<'PYSCRIPT'
import sys
import os

if len(sys.argv) < 2:
    raise SystemExit('Passwort-Argument fehlt')
password = sys.argv[1]

sys.path.insert(0, os.getcwd())

from app import create_app
from app.extensions import db
from app.models import User
from app.security import hash_password

app = create_app()
with app.app_context():
    username = app.config.get('ADMIN_USERNAME') or 'admin'

    u = User.query.filter_by(username=username).first()
    if u is None:
        admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
        if admin is not None:
            admin.username = username
            admin.password_hash = hash_password(password)
            admin.is_admin = True
            db.session.commit()
        else:
            u = User(username=username, password_hash=hash_password(password), is_admin=True)
            db.session.add(u)
            db.session.commit()
    else:
        u.password_hash = hash_password(password)
        u.is_admin = True
        db.session.commit()
PYSCRIPT

  # Save password to file for reference
  echo "${password}" > "${backend_dir}/.admin_password"
  chmod 600 "${backend_dir}/.admin_password"

  rm -f "${password_file}"
  note "Admin-Passwort wurde in DB gespeichert"
}

setup_logging() {
  note "Richte Log-Verzeichnis ein..."

  local log_dir="/var/log/birdshome"

  # Create log directory
  mkdir -p "${log_dir}"
  chown -R "${APP_USER}:${APP_GROUP}" "${log_dir}"
  chmod 775 "${log_dir}"

  # Create log files with correct permissions
  for log_file in birdshome.log snapshot.log timelapse.log upload.log stream.log motion.log; do
    touch "${log_dir}/${log_file}"
    chown "${APP_USER}:${APP_GROUP}" "${log_dir}/${log_file}"
    chmod 664 "${log_dir}/${log_file}"
  done

  # Setup logrotate for birdshome logs
  local logrotate_conf="/etc/logrotate.d/birdshome"
  cat > "${logrotate_conf}" <<'LOGROTATE'
/var/log/birdshome/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 664 @APP_USER@ @APP_GROUP@
    sharedscripts
    postrotate
        systemctl reload birdshome.service > /dev/null 2>&1 || true
    endscript
}
LOGROTATE

  sed -i "s/@APP_USER@/${APP_USER}/g" "${logrotate_conf}"
  sed -i "s/@APP_GROUP@/${APP_GROUP}/g" "${logrotate_conf}"
  chmod 644 "${logrotate_conf}"

  note "Log-Verzeichnis erstellt: ${log_dir}"
}

setup_sudoers() {
  note "Konfiguriere sudo-Rechte für ${APP_USER}..."

  local sudoers_file="/etc/sudoers.d/birdshome-stream"

  # Create sudoers file for app user to manage birdshome-stream service
  cat > "${sudoers_file}" <<SUDOERS
# Allow ${APP_USER} user to manage birdshome-stream service without password
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart birdshome-stream.service
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start birdshome-stream.service
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl stop birdshome-stream.service
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl status birdshome-stream.service
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl is-active birdshome-stream.service
SUDOERS

  # Set correct permissions for sudoers file
  chmod 0440 "${sudoers_file}"
  chown root:root "${sudoers_file}"

  # Validate sudoers file syntax
  if ! visudo -c -f "${sudoers_file}"; then
    note "WARNUNG: sudoers-Datei hat Syntaxfehler, entferne sie..."
    rm -f "${sudoers_file}"
    return 1
  fi

  note "sudo-Rechte für ${APP_USER} erfolgreich konfiguriert"
}

install_systemd() {
  note "Installiere systemd Services..."

  local unit_src unit_name unit_dst tmp
  local units=()
  local timers=()

  # Make helper scripts executable
  for script in run-snapshot.py run-timelapse.py run-stream.sh run-upload.py; do
    if [[ -f "${INSTALL_DIR}/backend/scripts/${script}" ]]; then
      chown "${APP_USER}:${APP_GROUP}" "${INSTALL_DIR}/backend/scripts/${script}"
      chmod +x "${INSTALL_DIR}/backend/scripts/${script}"
    fi
  done

  # Install .service files
  for unit_src in "${SCRIPT_DIR}/systemd/"*.service; do
    [[ -f "${unit_src}" ]] || continue
    unit_name="$(basename "${unit_src}")"
    unit_dst="/etc/systemd/system/${unit_name}"

    tmp="$(mktemp)"
    sed -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" -e "s|@APP_USER@|${APP_USER}|g" "${unit_src}" > "${tmp}"
    install -m 0644 "${tmp}" "${unit_dst}"
    rm -f "${tmp}"

    units+=("${unit_name}")
  done

  # Install .timer files
  for unit_src in "${SCRIPT_DIR}/systemd/"*.timer; do
    [[ -f "${unit_src}" ]] || continue
    unit_name="$(basename "${unit_src}")"
    unit_dst="/etc/systemd/system/${unit_name}"

    tmp="$(mktemp)"
    sed -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" -e "s|@APP_USER@|${APP_USER}|g" "${unit_src}" > "${tmp}"
    install -m 0644 "${tmp}" "${unit_dst}"
    rm -f "${tmp}"

    timers+=("${unit_name}")
  done

  systemctl daemon-reload

  [[ "${#units[@]}" -eq 0 ]] && die "Keine .service Dateien gefunden."

  # Enable all units and timers
  systemctl enable "${units[@]}"
  [[ "${#timers[@]}" -gt 0 ]] && systemctl enable "${timers[@]}"

  note "Starte Services in korrekter Reihenfolge..."

  # Define start order based on dependencies
  local ordered_services=(
    "birdshome-stream.service"    # 1. Stream (independent, but backend should be ready)
    "birdshome.service"           # 2. Backend first (database, API)
    "birdshome-jobs.service"      # 3. Job scheduler (depends on backend)
    "birdshome-daynight.service"    # 4. Stream (independent, but backend should be ready)
    "birdshome-motion.service"    # 5. Motion detection (depends on backend + stream)
  )

  # Start services in order with health checks
  for unit_name in "${ordered_services[@]}"; do
    if [[ " ${units[*]} " == *" ${unit_name} "* ]]; then
      note "Starte ${unit_name}..."
      systemctl restart "${unit_name}"

      # Wait for service to be active
      # Allow overriding the default startup timeout (in seconds) via SERVICE_START_TIMEOUT
      local wait_seconds="${SERVICE_START_TIMEOUT:-10}"
      local elapsed=0
      while [[ $elapsed -lt $wait_seconds ]]; do
        if systemctl is-active --quiet "${unit_name}"; then
          note "✓ ${unit_name} erfolgreich gestartet"
          break
        fi
        sleep 1
        elapsed=$((elapsed + 1))
      done

      # Check if service failed to start
      if ! systemctl is-active --quiet "${unit_name}"; then
        note "⚠ ${unit_name} wurde innerhalb von ${wait_seconds}s nicht aktiv"
        systemctl status "${unit_name}" --no-pager || true
      fi

      # Small delay between services
      sleep 2
    fi
  done

  # Start remaining services that weren't in ordered list
  for unit_name in "${units[@]}"; do
    if [[ ! " ${ordered_services[*]} " == *" ${unit_name} "* ]]; then
      note "Starte ${unit_name}..."
      systemctl restart "${unit_name}" || systemctl start "${unit_name}" || true
      sleep 1
    fi
  done

  # Start timers
  if [[ "${#timers[@]}" -gt 0 ]]; then
    note "Starte Timers..."
    for timer_name in "${timers[@]}"; do
      systemctl restart "${timer_name}" || systemctl start "${timer_name}" || true
    done
    note "✓ Timers gestartet: ${timers[*]}"
  fi

  # Final health check
  note "Prüfe Service-Status..."
  systemctl status birdshome.service --no-pager -l || true
}

setup_ufw_firewall() {
  [[ "${ENABLE_UFW}" -ne 1 ]] && return 0

  note "Installiere und konfiguriere UFW Firewall..."

  # Install UFW if not present
  if ! command -v ufw >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y --no-install-recommends ufw
  fi

  # Disable UFW temporarily for configuration
  ufw --force disable 2>/dev/null || true

  # Reset to defaults
  ufw --force reset

  # Default policies: deny incoming, allow outgoing
  ufw default deny incoming
  ufw default allow outgoing

  # Allow loopback
  ufw allow in on lo
  ufw allow out on lo

  # Allow SSH (important!)
  ufw allow 22/tcp comment 'SSH'

  # Allow HTTP and HTTPS
  ufw allow 80/tcp comment 'HTTP'
  ufw allow 443/tcp comment 'HTTPS'

  # Enable firewall
  ufw --force enable

  note "UFW Firewall konfiguriert: Port 22 (SSH), 80 (HTTP), 443 (HTTPS) erlaubt"
  ufw status verbose
}

configure_nginx() {
  local env_file="${INSTALL_DIR}/backend/.env"
  local mode domain cert_crt cert_key
  mode="${TLS_MODE}"
  domain="${BIRDSHOME_DOMAIN}"

  local nginx_dst="/etc/nginx/sites-available/birdshome"
  local tmp_cfg="$(mktemp)"

  if [[ "${mode}" == "none" ]]; then
    note "Konfiguriere nginx für HTTP..."
    sed -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
        -e "s|@DOMAIN@|${domain}|g" \
        "${SCRIPT_DIR}/nginx_http.conf" > "${tmp_cfg}"
  else
    note "Konfiguriere nginx für HTTPS (${mode})..."

    if [[ "${mode}" == "selfsigned" ]]; then
      # Generate self-signed certificate
      cert_crt="/etc/ssl/birdshome/birdshome.crt"
      cert_key="/etc/ssl/birdshome/birdshome.key"

      mkdir -p /etc/ssl/birdshome
      chmod 755 /etc/ssl/birdshome

      # Build SAN list
      local san_list=""
      IFS=',' read -ra SANS <<< "${TLS_SELF_SIGNED_SANS}"
      for san in "${SANS[@]}"; do
        san="$(echo "${san}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        if [[ "${san}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
          san_list="${san_list}IP:${san},"
        else
          san_list="${san_list}DNS:${san},"
        fi
      done
      san_list="${san_list%,}"

      note "Generiere self-signed Zertifikat für ${domain} (SANs: ${san_list})..."

      openssl req -x509 -nodes -days "${TLS_SELF_SIGNED_DAYS}" \
        -newkey rsa:2048 \
        -keyout "${cert_key}" \
        -out "${cert_crt}" \
        -subj "/CN=${domain}" \
        -addext "subjectAltName=${san_list}"

      chmod 644 "${cert_crt}"
      chmod 600 "${cert_key}"

    else
      # Let's Encrypt
      cert_crt="/etc/letsencrypt/live/${domain}/fullchain.pem"
      cert_key="/etc/letsencrypt/live/${domain}/privkey.pem"

      if [[ ! -f "${cert_crt}" ]]; then
        note "Erhalte Let's Encrypt Zertifikat für ${domain}..."

        # Create temporary HTTP config for certbot
        sed -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
            -e "s|@DOMAIN@|${domain}|g" \
            "${SCRIPT_DIR}/nginx_http.conf" > "${tmp_cfg}"
        install -m 0644 "${tmp_cfg}" "${nginx_dst}"
        ln -sf "${nginx_dst}" /etc/nginx/sites-enabled/birdshome
        rm -f /etc/nginx/sites-enabled/default || true
        nginx -t && systemctl reload nginx

        # Run certbot
        local staging_flag=""
        [[ "${LETSENCRYPT_STAGING}" -eq 1 ]] && staging_flag="--staging"

        certbot certonly --nginx \
          -d "${domain}" \
          --non-interactive \
          --agree-tos \
          --email "${LETSENCRYPT_EMAIL}" \
          ${staging_flag} || die "Let's Encrypt Zertifikat konnte nicht erhalten werden."

        note "Let's Encrypt Zertifikat erfolgreich erhalten."
      fi
    fi

    sed -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
        -e "s|@DOMAIN@|${domain}|g" \
        -e "s|@CERT_CRT@|${cert_crt}|g" \
        -e "s|@CERT_KEY@|${cert_key}|g" \
        "${SCRIPT_DIR}/nginx_ssl.conf" > "${tmp_cfg}"
  fi

  install -m 0644 "${tmp_cfg}" "${nginx_dst}"
  rm -f "${tmp_cfg}"

  rm -f /etc/nginx/sites-enabled/default || true
  ln -sf "${nginx_dst}" /etc/nginx/sites-enabled/birdshome
  nginx -t && systemctl restart nginx
  note "nginx Konfiguration abgeschlossen."
}

setup_ssh_keys() {
  [[ "${SSH_PUBLIC_KEY}" == "" ]] && return 0

  note "Richte SSH Public Key ein..."

  # Setup für pi user (falls vorhanden)
  for user in "pi" "${APP_USER}" "${SUDO_USER:-}"; do
    if [[ -z "${user}" ]] || ! id -u "${user}" >/dev/null 2>&1; then
      continue
    fi

    local user_home
    user_home="$(getent passwd "${user}" | cut -d: -f6)"

    if [[ -z "${user_home}" ]] || [[ ! -d "${user_home}" ]]; then
      continue
    fi

    local ssh_dir="${user_home}/.ssh"
    local authorized_keys="${ssh_dir}/authorized_keys"

    # Erstelle .ssh Verzeichnis
    mkdir -p "${ssh_dir}"
    touch "${authorized_keys}"

    # Füge Key hinzu wenn nicht bereits vorhanden
    if ! grep -qF "${SSH_PUBLIC_KEY}" "${authorized_keys}" 2>/dev/null; then
      echo "${SSH_PUBLIC_KEY}" >> "${authorized_keys}"
      note "SSH Key für ${user} hinzugefügt"
    else
      note "SSH Key für ${user} bereits vorhanden"
    fi

    # Setze korrekte Permissions
    chown -R "${user}:${user}" "${ssh_dir}"
    chmod 700 "${ssh_dir}"
    chmod 600 "${authorized_keys}"
  done

  # SSH härten
  note "Härte SSH-Konfiguration..."
  local sshd_config="/etc/ssh/sshd_config"
  local sshd_backup="${sshd_config}.birdshome.backup"

  # Backup erstellen
  if [[ ! -f "${sshd_backup}" ]]; then
    cp "${sshd_config}" "${sshd_backup}"
  fi

  # Sichere SSH-Einstellungen
  sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "${sshd_config}"
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "${sshd_config}"
  sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' "${sshd_config}"

  # Füge weitere Sicherheitseinstellungen hinzu falls nicht vorhanden
  if ! grep -q "^ClientAliveInterval" "${sshd_config}"; then
    echo "ClientAliveInterval 300" >> "${sshd_config}"
  fi
  if ! grep -q "^ClientAliveCountMax" "${sshd_config}"; then
    echo "ClientAliveCountMax 2" >> "${sshd_config}"
  fi

  # SSH neustarten
  systemctl restart sshd || systemctl restart ssh || true

  note "SSH Key Setup abgeschlossen"
}

install_tailscale() {
  [[ "${ENABLE_TAILSCALE}" != "1" ]] && return 0

  note "Installiere Tailscale..."

  # Prüfe ob bereits installiert
  if command -v tailscale >/dev/null 2>&1; then
    note "Tailscale ist bereits installiert"
    local version
    version="$(tailscale version | head -1)"
    note "Version: ${version}"
  else
    # Tailscale installieren
    note "Lade Tailscale Installer..."
    curl -fsSL https://tailscale.com/install.sh | sh || die "Tailscale Installation fehlgeschlagen"
  fi

  # Keepalive Script erstellen
  note "Erstelle Tailscale Keepalive Service..."

  mkdir -p "${INSTALL_DIR}/backend/scripts"

  cat > "${INSTALL_DIR}/backend/scripts/tailscale-keepalive.sh" <<'KEEPALIVE_SCRIPT'
#!/bin/bash
# Tailscale Connection Keepalive & Auto-Reconnect

LOG_FILE="/var/log/birdshome/tailscale-keepalive.log"
CHECK_INTERVAL=60

mkdir -p /var/log/birdshome
touch "$LOG_FILE"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

check_connection() {
    # Prüfe Tailscale Status
    if ! tailscale status >/dev/null 2>&1; then
        log "ERROR: Tailscale nicht verbunden, versuche Reconnect..."
        tailscale up
        return 1
    fi

    # Prüfe ob wir eine IP haben
    local ts_ip=$(tailscale ip -4 2>/dev/null)
    if [ -z "$ts_ip" ]; then
        log "ERROR: Keine Tailscale IP, versuche Reconnect..."
        tailscale up
        return 1
    fi

    # Prüfe Netzwerk-Konnektivität
    if ! ping -c 1 -W 5 login.tailscale.com >/dev/null 2>&1; then
        log "WARNING: Keine Verbindung zu Tailscale Coordinator"
        return 1
    fi

    return 0
}

log "Tailscale Keepalive gestartet (Check interval: ${CHECK_INTERVAL}s)"

while true; do
    if check_connection; then
        # Verbindung OK - kurzes Log alle 5 Minuten
        if [ $((SECONDS % 300)) -eq 0 ]; then
            ts_ip=$(tailscale ip -4)
            log "INFO: Verbindung OK (IP: $ts_ip)"
        fi
    else
        log "ERROR: Verbindung fehlgeschlagen, warte auf Reconnect..."
    fi

    sleep "$CHECK_INTERVAL"
done
KEEPALIVE_SCRIPT

  chmod +x "${INSTALL_DIR}/backend/scripts/tailscale-keepalive.sh"
  chown "${APP_USER}:${APP_GROUP}" "${INSTALL_DIR}/backend/scripts/tailscale-keepalive.sh"

  # Systemd Service erstellen
  cat > /etc/systemd/system/tailscale-keepalive.service <<SERVICE_FILE
[Unit]
Description=Tailscale Connection Keepalive for Birdshome
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/backend/scripts/tailscale-keepalive.sh
Restart=always
RestartSec=60
User=root

[Install]
WantedBy=multi-user.target
SERVICE_FILE

  systemctl daemon-reload
  systemctl enable tailscale-keepalive.service

  # Mit Auth Key verbinden wenn vorhanden
  if [[ -n "${TAILSCALE_AUTH_KEY}" ]]; then
    note "Verbinde mit Tailscale (Auth Key)..."
    local hostname
    hostname="birdshome-$(hostname)"
    tailscale up --authkey="${TAILSCALE_AUTH_KEY}" --hostname="${hostname}" || \
      note "WARNUNG: Tailscale Verbindung fehlgeschlagen - kann später manuell verbunden werden"

    # Starte Keepalive Service
    systemctl start tailscale-keepalive.service

    # Zeige Tailscale IP
    sleep 2
    local ts_ip
    ts_ip="$(tailscale ip -4 2>/dev/null || echo 'Noch nicht verbunden')"
    note "Tailscale IP: ${ts_ip}"
  else
    note "Tailscale installiert aber nicht verbunden."
    note "Verbinden mit: sudo tailscale up"
    note "Oder Auth Key verwenden: sudo tailscale up --authkey=<KEY>"
    note "Auth Keys erstellen: https://login.tailscale.com/admin/settings/keys"
  fi

  note "Tailscale Installation abgeschlossen"
}

print_summary() {

  note ""
  note "========================================="
  note "  Birdshome Installation abgeschlossen!"
  note "========================================="
  note ""
  if [ ${TLS_MODE} == "none" ]; then
      note "URL: http://${BIRDSHOME_DOMAIN}/"
  else
      note "URL: https://${BIRDSHOME_DOMAIN}/"
  fi
  note "Admin-Benutzer: ${ADMIN_USERNAME}"

  if [[ -f "${INSTALL_DIR}/backend/.admin_password" ]]; then
    note "(gespeichert in ${INSTALL_DIR}/backend/.admin_password)"
  fi

  note ""
  note "Nützliche Befehle:"
  note "  Logs anzeigen:    journalctl -u birdshome.service -f"
  note "  Status prüfen:    systemctl status birdshome.service"
  note "  Neustart:         systemctl restart birdshome.service"
  note "  Deinstallation:   sudo ${UNINSTALL_SCRIPT}"
  note ""

  if [[ "${TLS_MODE}" == "selfsigned" ]]; then
    note "HINWEIS: Self-signed Zertifikat wird Browser-Warnung auslösen."
    note "         Füge das Zertifikat zu deinen vertrauenswürdigen Zertifikaten hinzu:"
    note "         /etc/ssl/birdshome/birdshome.crt"
    note ""
  fi

  if [[ "${ENABLE_UFW}" -eq 1 ]]; then
    note "UFW Firewall ist aktiv. Zugelassene Ports: 22 (SSH), 80 (HTTP), 443 (HTTPS)"
    note ""
  fi

  # Tailscale Info
  if [[ "${ENABLE_TAILSCALE}" -eq 1 ]]; then
    note "--- Fernwartung via Tailscale ---"
    if command -v tailscale >/dev/null 2>&1; then
      local ts_status
      ts_status="$(tailscale status 2>&1 || echo 'Nicht verbunden')"

      if echo "${ts_status}" | grep -q "Logged out"; then
        note "Status: Installiert aber nicht verbunden"
        note "Verbinden: sudo tailscale up"
        note "Auth Keys: https://login.tailscale.com/admin/settings/keys"
      elif tailscale ip -4 >/dev/null 2>&1; then
        local ts_ip
        ts_ip="$(tailscale ip -4)"
        note "Status: Verbunden ✓"
        note "Tailscale IP: ${ts_ip}"
        note "SSH via Tailscale: ssh ${APP_USER}@${ts_ip}"
        note "Web via Tailscale: https://${ts_ip}/"
        note "Dashboard: https://login.tailscale.com/admin/machines"
      else
        note "Status: Verbindung wird hergestellt..."
      fi
    fi
    note ""
  fi

  # SSH Key Info
  if [[ -n "${SSH_PUBLIC_KEY}" ]]; then
    note "--- SSH Zugang ---"
    note "SSH Key wurde installiert für: pi, ${APP_USER}"
    note "SSH gehärtet: Root-Login deaktiviert, nur Key-Auth"
    note ""
  fi

  note "========================================="
}

handle_reboot() {
  # Handle system reboot if required (e.g., for I2C activation)

  # Check if reboot is needed
  if [[ "${REBOOT_REQUIRED}" -ne 1 ]]; then
    return 0
  fi

  note ""
  note "========================================="
  note "  NEUSTART ERFORDERLICH"
  note "========================================="
  note ""
  note "I2C wurde aktiviert und erfordert einen Systemneustart,"
  note "damit die Änderungen wirksam werden."
  note ""

  # Silent mode: auto-reboot
  if [[ "${SILENT_MODE}" -eq 1 ]]; then
    note "Silent-Modus: System wird in 5 Sekunden neu gestartet..."
    sleep 5
    reboot
    exit 0
  fi

  # Interactive mode with whiptail
  if is_interactive && have_whiptail; then
    if whiptail --title "Birdshome - Neustart erforderlich" --yesno \
      "I2C wurde aktiviert und erfordert einen Neustart.\n\nMöchten Sie das System jetzt neu starten?\n\n- JA: System wird sofort neu gestartet\n- NEIN: Neustart später manuell durchführen\n\nHINWEIS: I2C-Geräte funktionieren erst nach dem Neustart!" \
      16 78; then
      note "System wird neu gestartet..."
      sleep 2
      reboot
      exit 0
    else
      note ""
      note "WICHTIG: Bitte führen Sie einen manuellen Neustart durch:"
      note "  sudo reboot"
      note ""
      note "I2C-Geräte funktionieren erst nach dem Neustart!"
      note ""
    fi
  else
    # Non-interactive or no whiptail: show message only
    note "Bitte führen Sie einen manuellen Neustart durch:"
    note "  sudo reboot"
    note ""
  fi
}

main() {
  require_root

  # Parse command-line arguments
  parse_args "$@"

  # Collect all parameters (interactive or validate provided ones)
  collect_parameters

  # Show configuration summary
  print_configuration

  # Ask for confirmation in interactive mode with full configuration display
  if [[ "${SILENT_MODE}" -eq 0 ]] && is_interactive && have_whiptail; then
    # Build configuration summary for whiptail
    local summary=""
    summary+="Installation in: ${INSTALL_DIR}\n"
    summary+="Benutzer: ${APP_USER}\n"
    summary+="Gruppe: ${APP_GROUP}\n"
    summary+="\n"
    summary+="TLS-Modus: ${TLS_MODE}\n"
    summary+="Domain: ${BIRDSHOME_DOMAIN}\n"

    if [[ "${TLS_MODE}" == "letsencrypt" ]]; then
      summary+="Let's Encrypt Email: ${LETSENCRYPT_EMAIL}\n"
    elif [[ "${TLS_MODE}" == "selfsigned" ]]; then
      summary+="Self-signed SANs: ${TLS_SELF_SIGNED_SANS}\n"
    fi

    summary+="\n"
    summary+="Admin-Benutzer: ${ADMIN_USERNAME}\n"

    # Admin password status
    if [ -n "${ADMIN_PASSWORD}" ]; then
      summary+="Admin-Passwort: [gesetzt]\n"
    else
      summary+="Admin-Passwort: [wird generiert]\n"
    fi

    summary+="\n"
    summary+="Audio: ${AUDIO_SOURCE}\n"

    # UFW status
    if [ "${ENABLE_UFW}" -eq 1 ]; then
      summary+="UFW Firewall: aktiviert\n"
    else
      summary+="UFW Firewall: deaktiviert\n"
    fi

    summary+="\n"
    summary+="Node.js Version: ${NODE_MAJOR}\n"

    if ! whiptail --title "Birdshome Installation - Bestätigung" --yesno \
      "${summary}\n\nInstallation mit dieser Konfiguration starten?" 24 78; then
      die "Installation abgebrochen."
    fi
  fi

  note "Starte Installation..."

  # Run installation steps
  install_os_packages
  ensure_certbot
  ensure_node
  ensure_user
  enable_i2c
  rsync_repo
  bootstrap_env
  setup_backend
  build_frontend
  sync_admin_user_db
  setup_logging
  setup_sudoers
  install_systemd
  setup_ufw_firewall
  configure_nginx
  setup_ssh_keys
  install_tailscale

  print_summary

  # Handle reboot if required (e.g., for I2C)
  handle_reboot
}

main "$@"
