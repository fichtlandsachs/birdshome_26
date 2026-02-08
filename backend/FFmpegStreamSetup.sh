#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/birdshome/backend/.env"
OUT="/opt/birdshome/backend/app/static/hls"

# Hilfsfunktion zum sauberen Laden aus .env ohne 'source' Probleme
get_env_var() {
    local var_name=$1
    if [[ -f "$ENV_FILE" ]]; then
        grep "^${var_name}=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '\r' | sed "s/^'//;s/'$//;s/^\"//;s/\"$//"
    else
        echo ""
    fi
}

# Variablen laden
V_SRC_RAW=$(get_env_var "VIDEO_SOURCE")
[[ -z "$V_SRC_RAW" ]] && V_SRC_RAW=$(get_env_var "BIRDSHOME_VIDEO_SOURCE")

A_SRC_RAW=$(get_env_var "AUDIO_SOURCE")
[[ -z "$A_SRC_RAW" ]] && A_SRC_RAW=$(get_env_var "BIRDSHOME_AUDIO_SOURCE")

FPS=$(get_env_var "STREAM_FPS")
[[ -z "$FPS" ]] && FPS="30"

RES=$(get_env_var "STREAM_RES")
[[ -z "$RES" ]] && RES="640x480"

# Fallbacks für ffmpeg Syntax
V_SRC=${V_SRC_RAW:-"-f lavfi -i testsrc=size=${RES}:rate=${FPS}"}
A_SRC=${A_SRC_RAW:-"-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000"}

mkdir -p "$OUT"

echo "--- BIRDSHOME STREAM STARTUP ---"
echo "DEBUG: STREAM_FPS original: '$RAW_FPS'"
echo "DEBUG: FINAL_FPS used: '$FINAL_FPS'"
echo "DEBUG: FINAL_SCALE used: '$FINAL_SCALE'"
echo "DEBUG: FINAL_HEIGHT used: '$HEIGHT'"
echo "DEBUG: FINAL_WIDTH used: '$WIDTH'"
echo "DEBUG: AUDIO_RESSOURCE: '$BIRDSHOME_AUDIO_SOURCE'"
echo "camera: $BIRDSHOME_VIDEO_SOURCE"
echo "--------------------------------"


exec /usr/bin/rpicam-vid -t 0 --width "${RES%x*}" --height "${RES#*x}" --framerate "${FPS}" \
  --codec h264 --inline --profile baseline -o - | \
ffmpeg -hide_banner -loglevel warning \
  -fflags nobuffer -flags low_delay \
  -thread_queue_size 512 -f h264 -i - \
  -thread_queue_size 512 $BIRDSHOME_AUDIO_SOURCE \
  -vf scale="${RES%x*}":"${RES#*x}" -r "${FPS}" \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -c:a aac -b:a 128k \
  -f hls -hls_time 3 -hls_list_size 6 \
  -hls_flags delete_segments+append_list \
  -hls_segment_filename /opt/birdshome/backend/app/static/hls/segment_%05d.ts \
  /opt/birdshome/backend/app/static/hls/index.m3u8