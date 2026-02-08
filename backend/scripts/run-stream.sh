#!/usr/bin/env bash
set -euo pipefail

# Lade Umgebungsvariablen falls vorhanden
if [ -f "/opt/birdshome/backend/.env" ]; then
  # Exportiere Variablen, damit sie für ffmpeg verfügbar sind
  set -a
  source "/opt/birdshome/backend/.env"
  set +a
fi

# Fallbacks für wichtige Variablen
OUT="/opt/birdshome/backend/app/static/hls"
UDP_URL="udp://127.0.0.1:5004?pkt_size=1316"
# 1. Variablen laden und radikal säubern
RAW_FPS="${STREAM_FPS:-30}"
CLEAN_FPS=$(echo "$RAW_FPS" | tr -d -c '0-9')
# Falls CLEAN_FPS nach der Reinigung leer ist (weil nur Müll drin stand):
FINAL_FPS="${CLEAN_FPS:-30}"

RAW_RES="${STREAM_RES:-640x480}"
# Nur Zahlen und das 'x' behalten
CLEAN_RES=$(echo "$RAW_RES" | tr -d -c '0-9x')
[[ "$CLEAN_RES" =~ [0-9]+x[0-9]+ ]] || CLEAN_RES="640x480"
FINAL_SCALE="${CLEAN_RES/x/:}"
camera="v4l2 -framerate $FINAL_FPS -video_size $RAW_RES -i /dev/video0"

WIDTH="${CLEAN_RES%x*}"
HEIGHT="${CLEAN_RES#*x}"

# 2. Debug-Ausgabe in das System-Log (sichtbar mit journalctl)
echo "DEBUG: STREAM_FPS original: '$RAW_FPS'"
echo "DEBUG: FINAL_FPS used: '$FINAL_FPS'"
echo "DEBUG: FINAL_SCALE used: '$FINAL_SCALE'"
echo "DEBUG: FINAL_HEIGHT used: '$HEIGHT'"
echo "DEBUG: FINAL_WIDTH used: '$WIDTH'"
echo "DEBUG: AUDIO_RESSOURCE: '$BIRDSHOME_AUDIO_SOURCE'"
echo "camera: $camera"

# 3. Der Aufruf - Wir nutzen jetzt die sauberen Variablen mit festen Anführungszeichen
exec /usr/bin/rpicam-vid -t 0 \
  --width "$WIDTH" --height "$HEIGHT" --framerate "$RAW_FPS" \
  --codec h264 --inline --profile baseline --intra "$RAW_FPS" \
  -o - | \
ffmpeg -hide_banner -loglevel warning \
  -fflags nobuffer -flags low_delay -max_delay 0 \
  -thread_queue_size 512 -f h264 -i - \
  -thread_queue_size 512 $BIRDSHOME_AUDIO_SOURCE \
  -map 0:v:0 -map 1:a:0? \
  -c:v copy \
  -c:a aac -b:a 96k \
  -f tee -use_fifo 1 \
  "[f=hls:hls_time=1:hls_list_size=2:hls_flags=delete_segments+append_list+independent_segments:hls_segment_filename=${OUT}/segment_%05d.ts]${OUT}/index.m3u8|[f=mpegts]${UDP_URL}"
