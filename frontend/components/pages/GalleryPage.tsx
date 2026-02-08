import React, { useEffect, useState } from 'react';
import { Bird, XCircle, Calendar, Download, RefreshCw, Trash2 } from 'lucide-react';
import { api } from '../../lib/api';

interface GalleryItem {
  id: string;
  type: 'video' | 'photo' | 'timelapse';
  url: string;
  thumbnail: string;
  timestamp: string;
  hasBird: boolean;
}

const FilterButton: React.FC<{ label: string; active: boolean; onClick: () => void }> = ({ label, active, onClick }) => (
  <button
    onClick={onClick}
    className={`px-4 py-2 text-sm font-medium rounded-full transition-colors ${
      active ? 'bg-emerald-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'
    }`}
  >
    {label}
  </button>
);

interface GalleryPageProps {
  initialMediaType?: 'all' | 'photo' | 'video' | 'timelapse';
}

const GalleryPage: React.FC<GalleryPageProps> = ({ initialMediaType = 'all' }) => {
  const [filter, setFilter] = useState<'all' | 'birds' | 'nobirds'>('all');
  const [mediaTypeFilter, setMediaTypeFilter] = useState<'all' | 'photo' | 'video' | 'timelapse'>(initialMediaType);
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [hoveredVideo, setHoveredVideo] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.gallery(filter);
      // Sort by timestamp descending (newest first)
      let sorted = (data as GalleryItem[]).sort((a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );

      // Apply media type filter
      if (mediaTypeFilter !== 'all') {
        sorted = sorted.filter(item => item.type === mediaTypeFilter);
      }

      setItems(sorted);
    } catch (e: any) {
      setError(e?.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (item: GalleryItem) => {
    if (!confirm(`Möchten Sie dieses ${item.type === 'photo' ? 'Bild' : 'Video'} wirklich löschen?`)) {
      return;
    }

    setDeleting(item.id);
    try {
      await api.deleteMedia(item.id, item.type);
      setItems(items.filter(i => i.id !== item.id));
    } catch (e: any) {
      setError(e?.message || 'Fehler beim Löschen');
    } finally {
      setDeleting(null);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, mediaTypeFilter]);

  return (
    <div>
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <h2 className="text-3xl font-bold text-gray-800 dark:text-white">Gallery</h2>
        <button
          onClick={load}
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-100 text-sm font-medium flex items-center disabled:opacity-70"
        >
          <RefreshCw size={16} className="mr-2" /> Refresh
        </button>
      </div>

      <div className="mb-4 flex items-center space-x-2">
        <FilterButton label="All" active={mediaTypeFilter === 'all'} onClick={() => setMediaTypeFilter('all')} />
        <FilterButton label="Photos" active={mediaTypeFilter === 'photo'} onClick={() => setMediaTypeFilter('photo')} />
        <FilterButton label="Videos" active={mediaTypeFilter === 'video'} onClick={() => setMediaTypeFilter('video')} />
        <FilterButton label="Timelapses" active={mediaTypeFilter === 'timelapse'} onClick={() => setMediaTypeFilter('timelapse')} />
      </div>

      <div className="mb-6 flex items-center space-x-2">
        <FilterButton label="All" active={filter === 'all'} onClick={() => setFilter('all')} />
        <FilterButton label="With Birds" active={filter === 'birds'} onClick={() => setFilter('birds')} />
        <FilterButton label="Without Birds" active={filter === 'nobirds'} onClick={() => setFilter('nobirds')} />
      </div>

      {error && (
        <div className="mb-4 text-sm text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-300 p-3 rounded-lg">{error}</div>
      )}

      {loading ? (
        <div className="text-gray-600 dark:text-gray-300">Loading...</div>
      ) : items.length === 0 ? (
        <div className="text-gray-600 dark:text-gray-300">No items yet. Capture photos / upload videos to populate the database.</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {items.map((item) => (
            <div
              key={item.id}
              className="group relative bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden"
              onMouseEnter={() => item.type === 'video' || item.type === 'timelapse' ? setHoveredVideo(item.id) : null}
              onMouseLeave={() => setHoveredVideo(null)}
            >
              <img src={item.thumbnail} alt={item.type} className="w-full h-48 object-cover transition-transform duration-300 group-hover:scale-105" />
              {(item.type === 'video' || item.type === 'timelapse') && hoveredVideo === item.id && (
                <video
                  src={item.url}
                  className="absolute inset-0 w-full h-48 object-cover"
                  autoPlay
                  muted
                  loop
                />
              )}
              <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-50 transition-opacity duration-300 flex flex-col justify-between p-4 text-white">
                <div className="flex justify-between items-start opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <span className="text-xs font-bold uppercase bg-emerald-600 px-2 py-1 rounded">{item.type}</span>
                  {item.hasBird ? <Bird size={20} className="text-cyan-300" /> : <XCircle size={20} className="text-red-400" />}
                </div>
                <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <div className="flex items-center text-xs mb-2">
                    <Calendar size={14} className="mr-1" />
                    {new Date(item.timestamp).toLocaleString('de-DE')}
                  </div>
                  <div className="flex gap-2">
                    <a
                      href={item.url}
                      className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold py-2 px-3 rounded-lg flex items-center justify-center"
                      download
                    >
                      <Download size={16} className="mr-2" /> Download
                    </a>
                    <button
                      onClick={() => handleDelete(item)}
                      disabled={deleting === item.id}
                      className="bg-red-600 hover:bg-red-700 text-white text-sm font-bold py-2 px-3 rounded-lg flex items-center justify-center disabled:opacity-50"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default GalleryPage;
