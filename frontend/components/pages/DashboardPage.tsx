import React, { useEffect, useState } from 'react';
import {Cpu, HardDrive, Wifi, Sunrise, Egg, Bird, Video, Image, CheckCircle, XCircle} from 'lucide-react';
import { api } from '../../lib/api';

export type ApiError = { error: string };

let csrfToken: string | null = null;

type Language = 'de' | 'en' | 'es';

const translations = {
  de: {
    title: 'Vogel-Dashboard',
    loading: 'Lädt...',
    updating: 'Aktualisiere…',
    error: 'Fehler',
    noData: 'Keine Daten',
    stream: 'Stream',
    online: 'Online',
    offline: 'Offline',
    videos: 'Verfügbare Videos',
    recentPhotos: 'Letzte 10 Bilder',
    noPhotos: 'Noch keine Bilder vorhanden.',
    bioEvents: 'Biologische Ereignisse',
    noEvents: 'Noch keine Ereignisse.',
    recentActivity: 'Letzte Aktivitäten',
    streamUpdated: 'Stream-Status aktualisiert',
    galleryAvailable: 'Galerie verfügbar',
    dayNightSwitch: 'Tag/Nacht-Umschaltung (Platzhalter)',
    justNow: 'Gerade eben',
    photo: 'Foto'
  },
  en: {
    title: 'Bird Dashboard',
    loading: 'Loading...',
    updating: 'Updating…',
    error: 'Error',
    noData: 'No data',
    stream: 'Stream',
    online: 'Online',
    offline: 'Offline',
    videos: 'Available Videos',
    recentPhotos: 'Last 10 Photos',
    noPhotos: 'No photos available yet.',
    bioEvents: 'Biological Events',
    noEvents: 'No events yet.',
    recentActivity: 'Recent Activity',
    streamUpdated: 'Stream status updated',
    galleryAvailable: 'Gallery available',
    dayNightSwitch: 'Day/Night switching (placeholder)',
    justNow: 'Just now',
    photo: 'Photo'
  },
  es: {
    title: 'Panel de Pájaros',
    loading: 'Cargando...',
    updating: 'Actualizando…',
    error: 'Error',
    noData: 'Sin datos',
    stream: 'Transmisión',
    online: 'En línea',
    offline: 'Fuera de línea',
    videos: 'Videos Disponibles',
    recentPhotos: 'Últimas 10 Fotos',
    noPhotos: 'Aún no hay fotos disponibles.',
    bioEvents: 'Eventos Biológicos',
    noEvents: 'Aún no hay eventos.',
    recentActivity: 'Actividad Reciente',
    streamUpdated: 'Estado de transmisión actualizado',
    galleryAvailable: 'Galería disponible',
    dayNightSwitch: 'Cambio día/noche (marcador)',
    justNow: 'Ahora mismo',
    photo: 'Foto'
  }
};

type DashboardSummary = {
  stream: { running: boolean; mode: string };
  recent_photos: { id: number; url: string; timestamp: string }[];
  video_count: number;
};

type Page = 'dashboard' | 'stream' | 'gallery' | 'admin';
type MediaType = 'all' | 'photo' | 'video' | 'timelapse';

interface DashboardPageProps {
  onNavigate: (page: Page) => void;
  onNavigateToGallery: (mediaType: MediaType) => void;
}

const DashboardPage: React.FC<DashboardPageProps> = ({ onNavigate, onNavigateToGallery }) => {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [bioEvents, setBioEvents] = useState<{ id: number; kind: string; date: string; notes: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState<Language>('de');

  useEffect(() => {
    let alive = true;
    let isInitial = true;

    const fetchSummary = async () => {
      try {
        if (isInitial) setLoading(true);
        else setRefreshing(true);

        const data = await api.dashboardSummary();
        if (!alive) return;

        setSummary(data);
        setError(null);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : translations[lang].error);
      } finally {
        if (!alive) return;
        if (isInitial) {
          setLoading(false);
          isInitial = false;
        }
        setRefreshing(false);
      }
    };

    fetchSummary();
    const interval = setInterval(fetchSummary, 5000);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, [lang]);

  const t = translations[lang];

  if (loading) return <div className="p-6">{t.loading}</div>;
  if (error && !summary) return <div className="p-6 text-red-500">{t.error}: {error}</div>;
  if (!summary) return <div className="p-6">{t.noData}</div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-white">{t.title}</h1>
        <div className="flex items-center gap-4">
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {refreshing ? t.updating : error ? `${t.error}: ${error}` : ' '}
          </div>
          <div className="flex gap-2">
            <button onClick={() => setLang('de')} className={`px-2 py-1 text-xs rounded ${lang === 'de' ? 'bg-blue-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-300'}`}>DE</button>
            <button onClick={() => setLang('en')} className={`px-2 py-1 text-xs rounded ${lang === 'en' ? 'bg-blue-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-300'}`}>EN</button>
            <button onClick={() => setLang('es')} className={`px-2 py-1 text-xs rounded ${lang === 'es' ? 'bg-blue-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-300'}`}>ES</button>
          </div>
        </div>
      </div>

      {/* Stream Status - 2-zeilige Darstellung wie in HealthPage */}
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition-shadow"
        onClick={() => onNavigate('stream')}
      >
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Video className="mr-2" size={20} />
          {t.stream}
        </h2>
        <div className="flex items-center justify-between p-3 border dark:border-gray-700 rounded">
          <div className="flex items-center gap-3">
            {summary.stream.running ? (
              <CheckCircle size={20} className="text-green-500" />
            ) : (
              <XCircle size={20} className="text-red-500" />
            )}
            <div>
              <div className="font-medium text-gray-800 dark:text-white">{t.stream}</div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                {summary.stream.running ? t.online : t.offline}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Videos Count - 2-zeilige Darstellung */}
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition-shadow"
        onClick={() => onNavigateToGallery('video')}
      >
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Video className="mr-2" size={20} />
          {t.videos}
        </h2>
        <div className="flex items-center justify-between p-3 border dark:border-gray-700 rounded">
          <div className="flex items-center gap-3">
            <CheckCircle size={20} className="text-green-500" />
            <div>
              <div className="font-medium text-gray-800 dark:text-white">{t.videos}</div>
              <div className="text-sm text-gray-600 dark:text-gray-400">{summary.video_count}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Galerie */}
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition-shadow"
        onClick={() => onNavigateToGallery('photo')}
      >
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Image className="mr-2" size={20} />
          {t.recentPhotos}
        </h2>

        {summary.recent_photos.length === 0 ? (
          <div className="text-sm text-gray-500 dark:text-gray-400">{t.noPhotos}</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
            {summary.recent_photos.map((p) => (
              <div key={p.id} className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
                <img src={p.url} alt={`${t.photo} ${p.id}`} className="w-full h-28 object-cover" />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Biological Events - 2-zeilige Darstellung */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Bird className="mr-2" size={20} />
          {t.bioEvents}
        </h2>
        <div className="space-y-2">
          {bioEvents.length === 0 ? (
            <div className="text-sm text-gray-600 dark:text-gray-400">{t.noEvents}</div>
          ) : (
            bioEvents.map((event) => (
              <div key={event.id} className="flex items-center justify-between p-3 border dark:border-gray-700 rounded">
                <div className="flex items-center gap-3">
                  <CheckCircle size={20} className="text-green-500" />
                  <div>
                    <div className="font-medium text-gray-800 dark:text-white capitalize">{event.kind}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">{event.notes} • {event.date}</div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Recent Activity - 2-zeilige Darstellung */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800 dark:text-white">
          <Sunrise className="mr-2" size={20} />
          {t.recentActivity}
        </h2>
        <div className="space-y-2">
          <div className="flex items-center justify-between p-3 border dark:border-gray-700 rounded">
            <div className="flex items-center gap-3">
              <CheckCircle size={20} className="text-green-500" />
              <div>
                <div className="font-medium text-gray-800 dark:text-white">{t.streamUpdated}</div>
                <div className="text-sm text-gray-600 dark:text-gray-400">{t.justNow}</div>
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between p-3 border dark:border-gray-700 rounded">
            <div className="flex items-center gap-3">
              <CheckCircle size={20} className="text-green-500" />
              <div>
                <div className="font-medium text-gray-800 dark:text-white">{t.galleryAvailable}</div>
                <div className="text-sm text-gray-600 dark:text-gray-400">—</div>
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between p-3 border dark:border-gray-700 rounded">
            <div className="flex items-center gap-3">
              <CheckCircle size={20} className="text-green-500" />
              <div>
                <div className="font-medium text-gray-800 dark:text-white">{t.dayNightSwitch}</div>
                <div className="text-sm text-gray-600 dark:text-gray-400">—</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
