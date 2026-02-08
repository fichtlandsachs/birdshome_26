# Birdshome (Flask + React)

Dieses Repo kombiniert:
- **Flask** als Backend/API (Auth, CSRF, Streaming-Control, Healthcheck, Settings)
- **React (Vite)** als Frontend (Look & Feel gemäß UI-Entwurf: Sidebar, Emerald Accent, Cards, Dark Mode)

## Quickstart (Development)

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:3000
Backend: http://localhost:5000

## Production build (Frontend in Flask ausliefern)

```bash
cd frontend
npm install
npm run build
rm -rf ../backend/app/static/app
cp -r dist ../backend/app/static/app
```

Dann (Beispiel):
```bash
cd backend
source .venv/bin/activate
gunicorn -w 2 -b 127.0.0.1:5000 wsgi:app
```

## Login

Default-Admin wird beim Start aus `.env` gebootstrapped:
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

## Streaming

- Baseline: **HLS** via `ffmpeg` nach `backend/app/static/hls/index.m3u8`
- WebRTC ist in dieser Baseline als API-Stubs vorbereitet.

Um HLS zu starten:
- Admin Panel → Buttons (oder `POST /api/control/stream/start`)

## Hinweis

Auf Raspberry Pi sollten `VIDEO_SOURCE` und `AUDIO_SOURCE` in `.env` auf v4l2/alsa gesetzt werden.
