# Birdshome Remote Access Setup

Dieses Dokument beschreibt, wie du Tailscale VPN und SSH Keys für sichere Fernwartung deiner Birdshome Raspberry Pis einrichtest.

## 🚀 Schnellstart

### Option 1: Installation mit Tailscale (Empfohlen)

```bash
# SSH Key generieren (auf deinem PC)
ssh-keygen -t ed25519 -C "birdshome-remote"
cat ~/.ssh/id_ed25519.pub  # Kopiere diesen Key

# Tailscale Auth Key erstellen
# Gehe zu: https://login.tailscale.com/admin/settings/keys
# Erstelle einen "Auth Key" (reusable, ephemeral optional)

# Installation auf dem Raspberry Pi
sudo ./backend/scripts/install.sh \
  --tls-mode=selfsigned \
  --domain=birdshome.local \
  --admin-password=IhrSicheresPasswort \
  --enable-tailscale=1 \
  --tailscale-key=tskey-auth-XXXXX-XXXXX \
  --ssh-key="ssh-ed25519 AAAAC3NzaC1... user@hostname" \
  --silent
```

### Option 2: Manuelle Tailscale-Verbindung

```bash
# Installation ohne Auth Key
sudo ./backend/scripts/install.sh \
  --enable-tailscale=1 \
  --ssh-key="$(cat ~/.ssh/id_ed25519.pub)"

# Nach der Installation manuell verbinden
sudo tailscale up
# Folge dem Link im Browser zur Authentifizierung
```

## 📋 Voraussetzungen

### 1. Tailscale Account erstellen

1. Gehe zu https://login.tailscale.com/start
2. Melde dich mit Google, Microsoft oder GitHub an
3. Kostenlos bis 100 Geräte

### 2. SSH Key generieren (einmalig)

```bash
# Auf deinem PC/Laptop
ssh-keygen -t ed25519 -C "birdshome-fleet"
# Drücke Enter für Standard-Speicherort
# Optional: Passphrase eingeben

# Public Key anzeigen
cat ~/.ssh/id_ed25519.pub
```

## 🔧 Detaillierte Installation

### Schritt 1: Tailscale Auth Key erstellen (optional aber empfohlen)

1. Gehe zu https://login.tailscale.com/admin/settings/keys
2. Klicke auf "Generate auth key"
3. Optionen:
   - ✅ **Reusable** (für mehrere Pis)
   - ✅ **Ephemeral** (automatisch löschen wenn offline)
   - Gültigkeit: 90 Tage (empfohlen)
4. Kopiere den Key: `tskey-auth-XXXXX-XXXXX`

### Schritt 2: Birdshome installieren

**Mit allen Optionen:**

```bash
sudo ./backend/scripts/install.sh \
  --user=birdshome \
  --tls-mode=selfsigned \
  --domain=birdshome.local \
  --admin-user=admin \
  --admin-password=IhrSicheresPasswort \
  --enable-tailscale=1 \
  --tailscale-key=tskey-auth-XXXXX-XXXXX \
  --ssh-key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIxxx..." \
  --enable-ufw=1 \
  --silent
```

**Minimale Installation (interaktiv):**

```bash
sudo ./backend/scripts/install.sh \
  --ssh-key="$(cat ~/.ssh/id_ed25519.pub)"
```

### Schritt 3: Tailscale auf deinem PC installieren

#### Windows
1. Download: https://tailscale.com/download/windows
2. Installieren und anmelden

#### Linux
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

#### macOS
```bash
brew install tailscale
sudo tailscale up
```

## 🌐 Zugriff auf deine Raspberry Pis

### Tailscale IP finden

**Auf dem Raspberry Pi:**
```bash
tailscale ip -4
# Ausgabe: 100.x.x.x
```

**Im Tailscale Dashboard:**
https://login.tailscale.com/admin/machines

### SSH-Zugriff

```bash
# Via Tailscale IP (empfohlen)
ssh birdshome@100.x.x.x

# Oder mit pi user
ssh pi@100.x.x.x
```

### Web-Interface

**Im Browser:**
```
https://100.x.x.x/
```

**Zertifikatswarnung (bei self-signed):**
- Klicke auf "Erweitert" → "Unsichere Seite trotzdem laden"
- Normal bei self-signed Zertifikaten

## 🔍 Troubleshooting

### Tailscale Status prüfen

```bash
# Auf dem Raspberry Pi
sudo tailscale status
sudo systemctl status tailscaled
sudo systemctl status tailscale-keepalive
```

### Verbindungsprobleme

```bash
# Logs anzeigen
sudo journalctl -u tailscale-keepalive -f
sudo tail -f /var/log/birdshome/tailscale-keepalive.log

# Neuverbindung erzwingen
sudo tailscale down
sudo tailscale up
```

### SSH Verbindung schlägt fehl

```bash
# SSH Key prüfen
cat ~/.ssh/authorized_keys  # Auf dem Pi
ls -la ~/.ssh               # Permissions prüfen

# SSH Debug
ssh -v birdshome@100.x.x.x
```

### Tailscale neu installieren

```bash
# Auf dem Pi
sudo systemctl stop tailscale-keepalive
sudo tailscale down
sudo apt remove tailscale -y
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

## 📱 Mobile Zugriff

### iOS
https://apps.apple.com/app/tailscale/id1470499037

### Android
https://play.google.com/store/apps/details?id=com.tailscale.ipn

**Zugriff vom Smartphone:**
1. Tailscale App installieren
2. Mit gleichem Account anmelden
3. Im Browser: `https://100.x.x.x/`

## 🔐 Sicherheits-Best-Practices

### 1. SSH Härten (automatisch durch Script)

- ✅ Root-Login deaktiviert
- ✅ Passwort-Auth deaktiviert (nur Keys)
- ✅ Session-Timeout aktiv
- ✅ Nur über Tailscale erreichbar (empfohlen)

### 2. Firewall-Regeln

```bash
# SSH nur über Tailscale erlauben
sudo ufw deny 22
sudo ufw allow in on tailscale0 to any port 22

# Oder: SSH auf Tailscale-Interface binden
sudo nano /etc/ssh/sshd_config
# Füge hinzu:
ListenAddress 100.x.x.x  # Deine Tailscale IP
```

### 3. Tailscale ACLs (Access Control Lists)

Im Tailscale Dashboard (https://login.tailscale.com/admin/acls):

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:admin"],
      "dst": ["tag:birdshome:*"]
    }
  ],
  "tagOwners": {
    "tag:birdshome": ["admin@example.com"]
  }
}
```

## 🏢 Mehrere Raspberry Pis verwalten

### Fleet Deployment

```bash
# Gleichen SSH Key für alle Pis verwenden
SSH_KEY="$(cat ~/.ssh/id_ed25519.pub)"

# Installation auf Pi 1
ssh pi@pi1.local
sudo ./backend/scripts/install.sh \
  --enable-tailscale=1 \
  --tailscale-key=tskey-auth-XXXXX \
  --ssh-key="$SSH_KEY" \
  --silent

# Installation auf Pi 2
ssh pi@pi2.local
sudo ./backend/scripts/install.sh \
  --enable-tailscale=1 \
  --tailscale-key=tskey-auth-XXXXX \
  --ssh-key="$SSH_KEY" \
  --silent
```

### Zentrales Dashboard

https://login.tailscale.com/admin/machines

**Du siehst:**
- 🟢 Online/Offline Status
- 📍 Tailscale IPs (statisch)
- 📊 Traffic-Statistiken
- ⏰ Letzte Verbindung
- 🏷️ Hostname/Tags

## ❓ FAQ

### Muss ich Port-Forwarding einrichten?
**Nein!** Tailscale funktioniert hinter jeder Firewall ohne Port-Forwarding.

### Funktioniert es mit dynamischen IPs?
**Ja!** Die IP des Pis ist egal - Tailscale verbindet automatisch.

### Kostet Tailscale etwas?
**Nein** - bis 100 Geräte kostenlos. Perfekt für private Nutzung.

### Kann ich eigenen VPN-Server verwenden?
**Ja** - siehe Headscale (self-hosted Tailscale): https://github.com/juanfont/headscale

### Ist Tailscale sicher?
**Ja** - End-to-End verschlüsselt, basiert auf WireGuard, Zero Trust Architecture.

## 🔗 Nützliche Links

- Tailscale Dashboard: https://login.tailscale.com/admin/machines
- Auth Keys erstellen: https://login.tailscale.com/admin/settings/keys
- Tailscale Docs: https://tailscale.com/kb/
- Windows Client: https://tailscale.com/download/windows
- iOS App: https://apps.apple.com/app/tailscale/id1470499037
- Android App: https://play.google.com/store/apps/details?id=com.tailscale.ipn

## 📞 Support

Bei Problemen:
1. Prüfe Logs: `sudo journalctl -u tailscale-keepalive -f`
2. Status: `sudo tailscale status`
3. Reconnect: `sudo tailscale up`
4. GitHub Issues: https://github.com/anthropics/birdshome/issues
