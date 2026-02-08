import React, { useEffect, useState } from 'react';
import { FileText, Search, RefreshCw, AlertCircle, Filter, Download } from 'lucide-react';
import { api } from '../../lib/api';

interface LogEntry {
  timestamp: string;
  service: string;
  level: string;
  message: string;
}

export const LogsPage: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedService, setSelectedService] = useState<string>('all');
  const [selectedLevel, setSelectedLevel] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [lines, setLines] = useState<number>(500);

  const [debouncedSearch, setDebouncedSearch] = useState<string>('');

  // Debounce search term
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  const loadLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.adminLogs({
        service: selectedService !== 'all' ? selectedService : undefined,
        level: selectedLevel !== 'all' ? selectedLevel : undefined,
        lines,
        search: debouncedSearch || undefined,
      });
      setLogs(result.logs);
    } catch (e: any) {
      setError(e?.message || 'Failed to load logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [selectedService, selectedLevel, debouncedSearch, lines]);

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(parseInt(timestamp) / 1000);
    return date.toLocaleString('de-DE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const getLevelColor = (level: string): string => {
    switch (level) {
      case 'ERROR':
      case 'CRIT':
      case 'ALERT':
      case 'EMERG':
        return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20';
      case 'WARNING':
        return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20';
      case 'INFO':
      case 'NOTICE':
        return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20';
      case 'DEBUG':
        return 'text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50';
      default:
        return 'text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50';
    }
  };

  const getServiceColor = (service: string): string => {
    const colors: Record<string, string> = {
      main: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
      detect: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
      upload: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
      network: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
      timelapse: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300',
    };
    return colors[service] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
  };

  const exportLogs = () => {
    const content = logs.map(log =>
      `${formatTimestamp(log.timestamp)} [${log.service.toUpperCase()}] [${log.level}] ${log.message}`
    ).join('\n');

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `birdshome-logs-${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileText size={32} className="text-blue-600 dark:text-blue-400" />
          <div>
            <h1 className="text-2xl font-bold text-gray-800 dark:text-white">Service Logs</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {logs.length} Einträge geladen
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={exportLogs}
            disabled={logs.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            <Download size={18} />
            Export
          </button>
          <button
            onClick={loadLogs}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
            Aktualisieren
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-4 rounded-lg">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4 rounded-lg space-y-4">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          <Filter size={18} />
          Filter
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Service Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Service
            </label>
            <select
              value={selectedService}
              onChange={(e) => setSelectedService(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Alle Services</option>
              <option value="birdshome">Main (birdshome)</option>
              <option value="detect">Bird Detection</option>
              <option value="upload">Upload Service</option>
              <option value="network">Network Check</option>
              <option value="timelapse">Timelapse</option>
            </select>
          </div>

          {/* Level Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Log Level
            </label>
            <select
              value={selectedLevel}
              onChange={(e) => setSelectedLevel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Alle Level</option>
              <option value="ERROR">Errors</option>
              <option value="WARNING">Warnings</option>
              <option value="INFO">Info</option>
              <option value="DEBUG">Debug</option>
            </select>
          </div>

          {/* Lines */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Anzahl Zeilen
            </label>
            <select
              value={lines}
              onChange={(e) => setLines(parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
            >
              <option value="100">100</option>
              <option value="500">500</option>
              <option value="1000">1000</option>
              <option value="2000">2000</option>
              <option value="5000">5000</option>
            </select>
          </div>

          {/* Search */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Suche
            </label>
            <div className="relative">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Text suchen..."
                className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Logs */}
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500 dark:text-gray-400">
            <RefreshCw size={32} className="animate-spin mx-auto mb-2" />
            Logs werden geladen...
          </div>
        ) : logs.length === 0 ? (
          <div className="p-8 text-center text-gray-500 dark:text-gray-400">
            <FileText size={32} className="mx-auto mb-2 opacity-50" />
            Keine Logs gefunden
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 dark:bg-gray-700/50 border-b border-gray-200 dark:border-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Zeit
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Service
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Level
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Nachricht
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {logs.map((log, idx) => (
                  <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition">
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap font-mono">
                      {formatTimestamp(log.timestamp)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-1 text-xs font-medium rounded ${getServiceColor(log.service)}`}>
                        {log.service}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-1 text-xs font-medium rounded ${getLevelColor(log.level)}`}>
                        {log.level}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-800 dark:text-gray-200 font-mono break-all">
                      {log.message}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
