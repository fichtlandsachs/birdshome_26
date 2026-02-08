export type ApiError = { error: string };

let csrfToken: string | null = null;

export async function ensureCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  const res = await fetch('/api/csrf', { credentials: 'include' });
  if (!res.ok) throw new Error('csrf_init_failed');
  // Read from cookie (Double Submit). We cannot read HttpOnly, but CSRF cookie is non-HttpOnly by design.
  csrfToken = getCookie('birdshome_csrf');
  if (!csrfToken) throw new Error('csrf_cookie_missing');
  return csrfToken;
}

export function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});

  if (options.method && options.method.toUpperCase() !== 'GET') {
    const token = await ensureCsrf();
    headers.set('X-CSRF-Token', token);
    headers.set('Content-Type', headers.get('Content-Type') || 'application/json');
  }

  const res = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  });

  const isJson = (res.headers.get('content-type') || '').includes('application/json');
  const body: any = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    if (typeof body === 'object' && body?.error) {
      throw new Error(body.error);
    }
    throw new Error('request_failed');
  }
  return body as T;
}

export const api = {
  me: () => request<{ authenticated: boolean; username: string | null }>('/api/auth/me'),
  login: (username: string, password: string) => request<{ ok: boolean; username: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  }),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST', body: JSON.stringify({}) }),

  status: () => request<any>('/api/status'),
  getSettings: () => request<Record<string, string>>('/api/settings'),
  setSettings: (patch: Record<string, string>) => request<{ ok: boolean }>('/api/settings', {
    method: 'POST',
    body: JSON.stringify(patch),
  }),

  startStream: () => request<any>('/api/control/stream/start', { method: 'POST', body: JSON.stringify({}) }),
  stopStream: () => request<any>('/api/control/stream/stop', { method: 'POST', body: JSON.stringify({}) }),

  startMotion: () => request<any>('/api/control/motion/start', { method: 'POST', body: JSON.stringify({}) }),
  stopMotion: () => request<any>('/api/control/motion/stop', { method: 'POST', body: JSON.stringify({}) }),
  motionStatus: () => request<{ running: boolean; recording: boolean; last_motion: number; gpio_enabled?: boolean }>('/api/control/motion/status'),

  healthcheck: () => request<{ results: { name: string; status: 'ok' | 'fail'; details: string; duration: number }[] }>('/api/healthz'),
  adminHealth: () => request<{
    system: { cpu_percent: number; cpu_temp: number | null; mem_percent: number; disk_free_gb: number };
    stream: { running: boolean; mode: string; pid: number; started_at: string };
    health_checks: { name: string; status: 'ok' | 'fail'; details: string; duration: number }[];
    timers: { name: string; next: string; active: boolean }[];
    snapshot: { active: boolean; last_run: string | null; last_status: string };
    next_timelapse: { time: string; in_hours: number; in_minutes: number; human: string } | null;
  }>('/api/admin/health'),
  adminLogs: (params: { service?: string; level?: string; lines?: number; search?: string }) => {
    const query = new URLSearchParams();
    if (params.service) query.append('service', params.service);
    if (params.level) query.append('level', params.level);
    if (params.lines) query.append('lines', params.lines.toString());
    if (params.search) query.append('search', params.search);
    return request<{
      logs: { timestamp: string; service: string; level: string; message: string }[];
      total: number;
      service: string;
      level_filter: string;
      search: string;
    }>(`/api/admin/logs?${query.toString()}`);
  },
  gallery: (filter: 'all' | 'birds' | 'nobirds') => request<any[]>(`/api/media/gallery?filter=${encodeURIComponent(filter)}`),
  deleteMedia: (id: string, type: string) => request<{ ok: boolean }>('/api/media/delete', {
    method: 'DELETE',
    body: JSON.stringify({ id, type }),
  }),
  bioEvents: () => request<{ id: number; kind: string; date: string; notes: string }[]>('/api/bio/events'),

  dashboardSummary: () => request<{ stream: { running: boolean; mode: string }; recent_photos: { id: number; url: string; timestamp: string }[]; video_count: number }>('/api/dashboard/summary'),

  // WebRTC signaling
  webrtcOffer: (offer: { sdp: string; type: string }) => request<{ session_id: string; sdp: string; type: string }>('/api/webrtc/offer', {
    method: 'POST',
    body: JSON.stringify(offer),
  }),
  webrtcIce: (sessionId: string, candidate: RTCIceCandidate | null) => request<{ ok: boolean }>('/api/webrtc/ice', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, candidate }),
  }),
  webrtcClose: (sessionId: string) => request<{ ok: boolean }>('/api/webrtc/close', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  }),

  // Recording control
  getRecordingStatus: () => request<{ recording: boolean; started_at: number | null; duration: number; output_path: string | null; pid: number | null }>('/api/control/recording/status'),
  startRecording: () => request<{ ok: boolean; recording: boolean; output?: string; pid?: number; error?: string }>('/api/control/recording/start', {
    method: 'POST',
    body: JSON.stringify({}),
  }),
  stopRecording: () => request<{ ok: boolean; recording: boolean; path?: string; duration?: number; size_bytes?: number; video_id?: number; error?: string; warning?: string }>('/api/control/recording/stop', {
    method: 'POST',
    body: JSON.stringify({}),
  }),

  // Day/Night (IR) control
  getDayNightStatus: () => request<{ mode: 'day' | 'night' | 'auto'; auto_enabled: boolean }>('/api/control/daynight/status'),
  setDayNightMode: (mode: 'day' | 'night' | 'auto') => request<{ ok: boolean; mode: string }>('/api/control/daynight/switch', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  }),
};
