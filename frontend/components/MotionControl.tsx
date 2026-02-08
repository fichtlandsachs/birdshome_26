import React, { useEffect, useState } from 'react';
import { Activity, AlertCircle, Camera, Cpu } from 'lucide-react';
import { api } from '../lib/api';
import { ToggleSwitch } from './ToggleSwitch';

export const MotionControl: React.FC = () => {
  const [status, setStatus] = useState<{
    running: boolean;
    recording: boolean;
    last_motion: number;
    gpio_enabled?: boolean;
    framediff_enabled?: boolean;
    gpio_available?: boolean;
  } | null>(null);
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      const currentSettings = await api.getSettings();
      setSettings(currentSettings);

      const serviceEnabled = currentSettings.MOTION_SERVICE_ENABLED === '1';
      const gpioEnabled = currentSettings.MOTION_SENSOR_ENABLED === '1';
      const framediffEnabled = currentSettings.MOTION_FRAMEDIFF_ENABLED === '1';

      setStatus({
        running: serviceEnabled,
        recording: false,
        last_motion: 0,
        gpio_enabled: gpioEnabled,
        framediff_enabled: framediffEnabled,
        gpio_available: false
      });
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Failed to load status');
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleServiceToggle = async (enabled: boolean) => {
    setLoading(true);
    try {
      if (enabled) {
        const result = await api.startMotion();
        if (!result.ok) {
          setError(result.error || 'Failed to start motion service');
        }
      } else {
        await api.stopMotion();
      }
      await loadStatus();
    } catch (e: any) {
      setError(e?.message || 'Fehler beim Umschalten');
    } finally {
      setLoading(false);
    }
  };

  const handleMethodToggle = async (method: 'framediff' | 'gpio', enabled: boolean) => {
    // Check if we're trying to disable the last active method
    const framediffEnabled = method === 'framediff' ? enabled : (status?.framediff_enabled || false);
    const gpioEnabled = method === 'gpio' ? enabled : (status?.gpio_enabled || false);

    if (!framediffEnabled && !gpioEnabled) {
      setError('Mindestens eine Erkennungsmethode (Frame-Diff oder GPIO) muss aktiviert sein');
      return;
    }

    setLoading(true);
    try {
      const key = method === 'framediff' ? 'MOTION_FRAMEDIFF_ENABLED' : 'MOTION_SENSOR_ENABLED';
      await api.saveSettings({ [key]: enabled ? '1' : '0' });

      // If service is running, restart it to apply changes
      if (status?.running) {
        await api.stopMotion();
        await new Promise(resolve => setTimeout(resolve, 500)); // Brief pause
        const result = await api.startMotion();
        if (!result.ok) {
          setError(result.error || 'Failed to restart motion service');
        }
      }

      await loadStatus();
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Fehler beim Umschalten');
    } finally {
      setLoading(false);
    }
  };

  const activeMethods: string[] = [];
  if (status?.framediff_enabled) activeMethods.push('Frame-Diff');
  if (status?.gpio_enabled) activeMethods.push('GPIO-Sensor');

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6 rounded-lg shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Activity size={24} className="text-emerald-600 dark:text-emerald-400" />
          <div>
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white">Bewegungserkennung</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Automatische Videoaufnahme bei erkannter Bewegung
              {activeMethods.length > 0 && ` (${activeMethods.join(' + ')})`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 text-sm">
            <div className={`w-2 h-2 rounded-full ${status?.running ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-700 dark:text-gray-300">
              {status?.running ? 'In Betrieb' : 'Abgeschaltet'}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {/* Service toggle */}
      <div className="mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-3">
          <ToggleSwitch
            enabled={status?.running || false}
            onChange={handleServiceToggle}
            disabled={loading}
            loading={loading}
          />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {loading ? 'Umschalten...' : status?.running ? 'Service aktiviert' : 'Service deaktiviert'}
          </span>
        </div>
      </div>

      {/* Detection methods */}
      <div className="space-y-3">
        <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
          Erkennungsmethoden
        </div>

        {/* Frame-Diff toggle */}
        <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <div className="flex items-center gap-3">
            <Camera size={18} className="text-blue-600 dark:text-blue-400" />
            <div>
              <div className="text-sm font-medium text-gray-800 dark:text-white">Frame Differencing</div>
              <div className="text-xs text-gray-600 dark:text-gray-400">Optische Bewegungserkennung</div>
            </div>
          </div>
          <ToggleSwitch
            enabled={status?.framediff_enabled || false}
            onChange={(enabled) => handleMethodToggle('framediff', enabled)}
            disabled={loading}
            loading={loading}
          />
        </div>

        {/* GPIO toggle */}
        <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <div className="flex items-center gap-3">
            <Cpu size={18} className="text-purple-600 dark:text-purple-400" />
            <div>
              <div className="text-sm font-medium text-gray-800 dark:text-white">GPIO Sensor (PIR)</div>
              <div className="text-xs text-gray-600 dark:text-gray-400">Hardware Bewegungssensor</div>
            </div>
          </div>
          <ToggleSwitch
            enabled={status?.gpio_enabled || false}
            onChange={(enabled) => handleMethodToggle('gpio', enabled)}
            disabled={loading}
            loading={loading}
          />
        </div>
      </div>

      <div className="mt-4 text-xs text-gray-500 dark:text-gray-400 italic">
        Mindestens eine Erkennungsmethode muss aktiviert sein
      </div>
    </div>
  );
};
