import React, { useEffect, useState, useCallback } from 'react';
import { Activity, Cpu, HardDrive, Clock, Camera, Video, AlertTriangle, CheckCircle, XCircle, Loader } from 'lucide-react';
import { api } from '../../lib/api';

type Language = 'de' | 'en' | 'es';

const translations = {
  de: {
    title: 'System-Status',
    loading: 'Lädt...',
    error: 'Fehler',
    noData: 'Keine Daten',
    systemResources: 'System-Ressourcen',
    cpuUsage: 'CPU Auslastung',
    cpuTemp: 'CPU Temperatur',
    ramUsage: 'RAM Auslastung',
    freeSpace: 'Freier Speicher',
    cpuCritical: 'CPU-Temperatur kritisch',
    checkCooling: 'Kühlung prüfen!',
    streamStatus: 'Stream-Status',
    online: 'Online',
    offline: 'Offline',
    mode: 'Mode',
    timelapseServices: 'Zeitraffer-Services',
    snapshotService: 'Snapshot-Service',
    active: 'Aktiv',
    inactive: 'Inaktiv',
    lastRun: 'Letzte Ausführung',
    nextTimelapse: 'Nächstes Zeitraffer-Video',
    in: 'in',
    scheduledFor: 'Geplant für',
    notScheduled: 'Nicht geplant',
    systemdTimers: 'Systemd-Timer',
    healthChecks: 'Systemprüfungen'
  },
  en: {
    title: 'System Status',
    loading: 'Loading...',
    error: 'Error',
    noData: 'No data',
    systemResources: 'System Resources',
    cpuUsage: 'CPU Usage',
    cpuTemp: 'CPU Temperature',
    ramUsage: 'RAM Usage',
    freeSpace: 'Free Space',
    cpuCritical: 'CPU temperature critical',
    checkCooling: 'Check cooling!',
    streamStatus: 'Stream Status',
    online: 'Online',
    offline: 'Offline',
    mode: 'Mode',
    timelapseServices: 'Timelapse Services',
    snapshotService: 'Snapshot Service',
    active: 'Active',
    inactive: 'Inactive',
    lastRun: 'Last run',
    nextTimelapse: 'Next Timelapse Video',
    in: 'in',
    scheduledFor: 'Scheduled for',
    notScheduled: 'Not scheduled',
    systemdTimers: 'Systemd Timers',
    healthChecks: 'Health Checks'
  },
  es: {
    title: 'Estado del Sistema',
    loading: 'Cargando...',
    error: 'Error',
    noData: 'Sin datos',
    systemResources: 'Recursos del Sistema',
    cpuUsage: 'Uso de CPU',
    cpuTemp: 'Temperatura CPU',
    ramUsage: 'Uso de RAM',
    freeSpace: 'Espacio Libre',
    cpuCritical: 'Temperatura de CPU crítica',
    checkCooling: '¡Verificar refrigeración!',
    streamStatus: 'Estado de Transmisión',
    online: 'En línea',
    offline: 'Fuera de línea',
    mode: 'Modo',
    timelapseServices: 'Servicios de Timelapse',
    snapshotService: 'Servicio de Instantáneas',
    active: 'Activo',
    inactive: 'Inactivo',
    lastRun: 'Última ejecución',
    nextTimelapse: 'Próximo Video Timelapse',
    in: 'en',
    scheduledFor: 'Programado para',
    notScheduled: 'No programado',
    systemdTimers: 'Temporizadores Systemd',
    healthChecks: 'Verificaciones de Estado'
  }
};

type HealthCheck = {
  name: string;
  status: 'ok' | 'fail' | 'loading';
  details: string;
  duration: number;
};

type HealthData = {
  system: { cpu_percent: number; cpu_temp: number | null; mem_percent: number; disk_free_gb: number };
  stream: { running: boolean; mode: string; pid: number; started_at: string };
  timers: { name: string; next: string; active: boolean }[];
  snapshot: { active: boolean; last_run: string | null; last_status: string };
  next_timelapse: { time: string; in_hours: number; in_minutes: number; human: string } | null;
};

const HEALTH_CHECKS = [
  { id: 'hidrive_connection', name: 'HiDrive Connection' },
  { id: 'hidrive_upload', name: 'HiDrive Test Upload' },
  { id: 'camera', name: 'Camera Availability' },
  { id: 'microphone', name: 'Microphone Availability' },
  { id: 'disk', name: 'Disk Space' },
  { id: 'scheduler', name: 'Scheduler Status' },
  { id: 'streaming', name: 'Streaming Pipeline' },
  { id: 'motion_service', name: 'Motion Service' },
  { id: 'snapshot_service', name: 'Snapshot Service' },
  { id: 'timers', name: 'Systemd Timers' },
];

const getTempColor = (temp: number | null): string => {
  if (temp === null) return 'text-gray-500';
  if (temp < 50) return 'text-blue-500';
  if (temp < 70) return 'text-green-500';
  if (temp < 80) return 'text-yellow-500';
  return 'text-red-500';
};

const HealthPage: React.FC = () => {
  const [data, setData] = useState<HealthData | null>(null);
  const [healthChecks, setHealthChecks] = useState<HealthCheck[]>(
    HEALTH_CHECKS.map(check => ({
      name: check.name,
      status: 'loading' as const,
      details: '',
      duration: 0
    }))
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState<Language>('de');

  // Fetch individual health check
  const fetchHealthCheck = useCallback(async (checkId: string, index: number) => {
    try {
      const response = await fetch(`/api/admin/health/check/${checkId}`, {
        credentials: 'include'
      });

      if (!response.ok) {
        throw new Error('Check failed');
      }

      const result = await response.json();

      setHealthChecks(prev => {
        const updated = [...prev];
        updated[index] = {
          name: HEALTH_CHECKS[index].name,
          status: result.status,
          details: result.details,
          duration: result.duration
        };
        return updated;
      });
    } catch (err) {
      setHealthChecks(prev => {
        const updated = [...prev];
        updated[index] = {
          name: HEALTH_CHECKS[index].name,
          status: 'fail',
          details: err instanceof Error ? err.message : 'Unknown error',
          duration: 0
        };
        return updated;
      });
    }
  }, []);

  // Fetch basic health data (system, stream, timers, snapshot)
  const fetchBasicHealth = useCallback(async () => {
    try {
      const result = await api.adminHealth();
      setData({
        system: result.system,
        stream: result.stream,
        timers: result.timers,
        snapshot: result.snapshot,
        next_timelapse: result.next_timelapse
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : translations[lang].error);
    } finally {
      setLoading(false);
    }
  }, [lang]);

  // Initial load: fetch basic data immediately, then load checks progressively
  useEffect(() => {
    let alive = true;

    const initialize = async () => {
      // First: Load basic system info (fast)
      await fetchBasicHealth();

      if (!alive) return;

      // Then: Load health checks progressively (in parallel)
      HEALTH_CHECKS.forEach((check, index) => {
        fetchHealthCheck(check.id, index);
      });
    };

    initialize();

    // Refresh interval for basic health data
    const basicInterval = setInterval(fetchBasicHealth, 5000);

    // Refresh interval for health checks (less frequent)
    const checksInterval = setInterval(() => {
      if (alive) {
        HEALTH_CHECKS.forEach((check, index) => {
          fetchHealthCheck(check.id, index);
        });
      }
    }, 30000); // Every 30 seconds

    return () => {
      alive = false;
      clearInterval(basicInterval);
      clearInterval(checksInterval);
    };
  }, [lang, fetchBasicHealth, fetchHealthCheck]);

  const t = translations[lang];

  if (loading) return <div className="p-6">{t.loading}</div>;
  if (error) return <div className="p-6 text-red-500">{t.error}: {error}</div>;
  if (!data) return <div className="p-6">{t.noData}</div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-white">{t.title}</h1>
        <div className="flex gap-2">
          <button onClick={() => setLang('de')} className={`px-2 py-1 text-xs rounded ${lang === 'de' ? 'bg-blue-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-300'}`}>DE</button>
          <button onClick={() => setLang('en')} className={`px-2 py-1 text-xs rounded ${lang === 'en' ? 'bg-blue-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-300'}`}>EN</button>
          <button onClick={() => setLang('es')} className={`px-2 py-1 text-xs rounded ${lang === 'es' ? 'bg-blue-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-300'}`}>ES</button>
        </div>
      </div>

      {/* System Resources */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Cpu className="mr-2" size={20} />
          {t.systemResources}
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded">
            <div className="text-sm text-gray-600 dark:text-gray-400">{t.cpuUsage}</div>
            <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{data.system.cpu_percent}%</div>
          </div>

          <div className="bg-orange-50 dark:bg-orange-900/20 p-4 rounded">
            <div className="text-sm text-gray-600 dark:text-gray-400">{t.cpuTemp}</div>
            <div className={`text-2xl font-bold ${getTempColor(data.system.cpu_temp)}`}>
              {data.system.cpu_temp !== null ? `${data.system.cpu_temp}°C` : 'N/A'}
            </div>
          </div>

          <div className="bg-green-50 dark:bg-green-900/20 p-4 rounded">
            <div className="text-sm text-gray-600 dark:text-gray-400">{t.ramUsage}</div>
            <div className="text-2xl font-bold text-green-600 dark:text-green-400">{data.system.mem_percent}%</div>
          </div>

          <div className="bg-purple-50 dark:bg-purple-900/20 p-4 rounded">
            <div className="text-sm text-gray-600 dark:text-gray-400">{t.freeSpace}</div>
            <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">{data.system.disk_free_gb} GB</div>
          </div>
        </div>

        {data.system.cpu_temp !== null && data.system.cpu_temp > 80 && (
          <div className="mt-4 p-3 bg-red-100 dark:bg-red-900/20 border border-red-400 dark:border-red-600 text-red-700 dark:text-red-400 rounded flex items-center">
            <AlertTriangle size={20} className="mr-2" />
            {t.cpuCritical}: {data.system.cpu_temp}°C - {t.checkCooling}
          </div>
        )}
      </div>

      {/* Stream Status */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Video className="mr-2" size={20} />
          {t.streamStatus}
        </h2>
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${data.stream.running ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <span className="font-medium text-gray-800 dark:text-white">
            {data.stream.running ? t.online : t.offline}
          </span>
          <span className="text-sm text-gray-600 dark:text-gray-400">•</span>
          <span className="text-sm text-gray-600 dark:text-gray-400">{t.mode}: {data.stream.mode}</span>
          {data.stream.pid > 0 && (
            <>
              <span className="text-sm text-gray-600 dark:text-gray-400">•</span>
              <span className="text-sm text-gray-600 dark:text-gray-400">PID: {data.stream.pid}</span>
            </>
          )}
        </div>
      </div>

      {/* Timelapse Services */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Camera className="mr-2" size={20} />
          {t.timelapseServices}
        </h2>

        <div className="space-y-4">
          {/* Snapshot Status */}
          <div className="border dark:border-gray-700 rounded p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-medium text-gray-800 dark:text-white">{t.snapshotService}</h3>
              <span className={`px-3 py-1 rounded text-sm ${data.snapshot.active ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400' : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400'}`}>
                {data.snapshot.active ? (data.snapshot.last_run ? t.active : '') : t.inactive}
              </span>
            </div>
            {data.snapshot.last_run && (
              <div className="text-sm text-gray-600 dark:text-gray-400">
                {t.lastRun}: {data.snapshot.last_run}
              </div>
            )}
          </div>

          {/* Next Timelapse */}
          <div className="border dark:border-gray-700 rounded p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-medium text-gray-800 dark:text-white">{t.nextTimelapse}</h3>
              {data.next_timelapse && (
                <span className="px-3 py-1 rounded text-sm bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400 flex items-center">
                  <Clock size={16} className="mr-1" />
                  {t.in} {data.next_timelapse.human}
                </span>
              )}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {data.next_timelapse
                ? `${t.scheduledFor}: ${new Date(data.next_timelapse.time).toLocaleString(lang === 'de' ? 'de-DE' : lang === 'es' ? 'es-ES' : 'en-US')}`
                : t.notScheduled}
            </div>
          </div>

          {/* Timers */}
          {data.timers.length > 0 && (
            <div className="border dark:border-gray-700 rounded p-4">
              <h3 className="font-medium mb-2 text-gray-800 dark:text-white">{t.systemdTimers}</h3>
              <div className="space-y-2">
                {data.timers.map((timer, idx) => (
                  <div key={idx} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700 dark:text-gray-300">{timer.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-600 dark:text-gray-400">{timer.next}</span>
                      <span className={`w-2 h-2 rounded-full ${timer.active ? 'bg-green-500' : 'bg-gray-400'}`}></span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Health Checks */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Activity className="mr-2" size={20} />
          {t.healthChecks}
        </h2>
        <div className="space-y-2">
          {healthChecks.map((check, idx) => (
            <div key={idx} className="flex items-center justify-between p-3 border dark:border-gray-700 rounded">
              <div className="flex items-center gap-3">
                {check.status === 'loading' ? (
                  <Loader size={20} className="text-blue-500 animate-spin" />
                ) : check.status === 'ok' ? (
                  <CheckCircle size={20} className="text-green-500" />
                ) : (
                  <XCircle size={20} className="text-red-500" />
                )}
                <div>
                  <div className="font-medium text-gray-800 dark:text-white">{check.name}</div>
                  <div className="text-sm text-gray-600 dark:text-gray-400">
                    {check.status === 'loading' ? t.loading : check.details}
                  </div>
                </div>
              </div>
              {check.status !== 'loading' && (
                <span className="text-xs text-gray-500 dark:text-gray-500">{check.duration}ms</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default HealthPage;
