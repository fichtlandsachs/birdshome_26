import React, { useEffect, useMemo, useState } from 'react';
import { Video, Camera, UploadCloud, Cpu, SunMoon, Shield, Activity, Save, AlertCircle, FileText } from 'lucide-react';
import { api } from '../../lib/api';
import HealthPage from './HealthPage';
import { LogsPage } from './LogsPage';
import { MotionControl } from '../MotionControl';

type FieldType = 'text' | 'number' | 'select' | 'toggle' | 'password';
type FieldDef = {
  key: string;
  label: string;
  hint?: string;
  type?: FieldType;
  options?: { label: string; value: string }[];
};

type FieldGroup = {
  title: string;
  description?: string;
  fields: FieldDef[];
};

const AdminPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('health');

  const [settings, setSettings] = useState<Record<string, string>>({});
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const s = await api.getSettings();
        setSettings(s);
        setSettingsLoaded(true);
      } catch {
        setSettingsLoaded(false);
      }
    })();
  }, []);

  const save = async () => {
    setSaveState('saving');
    setSaveError(null);
    try {
      await api.setSettings(settings);
      setSaveState('saved');
      setTimeout(() => setSaveState('idle'), 1500);
    } catch (e: any) {
      setSaveState('error');
      setSaveError(e?.message || 'Fehler beim Speichern der Einstellungen');
      setTimeout(() => {
        setSaveState('idle');
        setSaveError(null);
      }, 5000);
    }
  };

  const tabs = [
    { id: 'health', label: 'System Health', icon: <Activity /> },
    { id: 'video', label: 'Video/Stream', icon: <Video /> },
    { id: 'photos', label: 'Photos/Timelapse', icon: <Camera /> },
    { id: 'upload', label: 'Upload/Retention', icon: <UploadCloud /> },
    { id: 'ai', label: 'AI Detection', icon: <Cpu /> },
    { id: 'ir', label: 'IR/Light', icon: <SunMoon /> },
    { id: 'system', label: 'System/Security', icon: <Shield /> },
    { id: 'logs', label: 'Service Logs', icon: <FileText /> },
  ];

  // Grouped fields for video tab
  const fieldGroupsByTab: Record<string, FieldGroup[]> = useMemo(
    () => ({
      video: [
        {
          title: 'Technische Einstellungen',
          description: 'Stream-Konfiguration und technische Parameter',
          fields: [
            {
              key: 'STREAM_MODE',
              label: 'Stream Mode',
              hint: 'HLS oder WEBRTC',
              type: 'select',
              options: [
                { label: 'HLS', value: 'HLS' },
                { label: 'WEBRTC', value: 'WEBRTC' },
              ],
            },
            { key: 'STREAM_RES', label: 'Stream Resolution', hint: 'z.B. 1280x720', type: 'text' },
            { key: 'STREAM_FPS', label: 'Stream FPS', hint: 'z.B. 30', type: 'number' },
            { key: 'HLS_SEGMENT_SECONDS', label: 'HLS Segment Seconds', hint: '2–4 empfohlen', type: 'number' },
            { key: 'HLS_PLAYLIST_SIZE', label: 'HLS Playlist Size', hint: 'z.B. 6', type: 'number' },
            { key: 'STREAM_UDP_URL', label: 'Stream UDP URL', hint: 'z.B. udp://127.0.0.1:5004?pkt_size=1316', type: 'text' },
            { key: 'MOTION_SOURCE', label: 'Motion Source', hint: 'UDP/RTSP URL oder leer für VIDEO_SOURCE', type: 'text' },
          ],
        },
        {
          title: 'Videoeinstellungen',
          description: 'Aufnahme-Parameter und Datei-Konfiguration',
          fields: [
            { key: 'PREFIX', label: 'Filename Prefix', hint: 'z.B. nest_', type: 'text' },
            { key: 'RECORD_RES', label: 'Record Resolution', hint: 'z.B. 1920x1080', type: 'text' },
            { key: 'RECORD_FPS', label: 'Record FPS', hint: 'z.B. 30', type: 'number' },
            {
              key: 'VIDEO_ROTATION',
              label: 'Video Rotation',
              hint: 'Bild drehen (0°, 90°, 180°, 270°)',
              type: 'select',
              options: [
                { label: '0° (Normal)', value: '0' },
                { label: '90° (Rechts)', value: '90' },
                { label: '180° (Kopfüber)', value: '180' },
                { label: '270° (Links)', value: '270' },
              ],
            },
          ],
        },
        {
          title: 'Bewegungserkennung',
          description: 'Optische und Sensor-basierte Bewegungserkennung',
          fields: [
            { key: 'MOTION_THRESHOLD', label: 'Motion Threshold', hint: 'Empfindlichkeit (15-50, niedriger = empfindlicher)', type: 'number' },
            { key: 'MOTION_DURATION_S', label: 'Recording Duration (s)', hint: 'Aufnahmedauer in Sekunden (z.B. 10)', type: 'number' },
            { key: 'MOTION_COOLDOWN_S', label: 'Cooldown (s)', hint: 'Pause zwischen Aufnahmen in Sekunden (z.B. 5)', type: 'number' },
            { key: 'MOTION_SENSOR_GPIO', label: 'Motion Sensor GPIO Pin', hint: 'GPIO Pin (BCM) für Bewegungsmelder (z.B. 22)', type: 'number' },
          ],
        },
      ],
    }),
    []
  );

  // UI is intentionally scoped: each tab only shows fields relevant to its function.
  const fieldsByTab: Record<string, FieldDef[]> = useMemo(
    () => ({
      video: [], // Using fieldGroupsByTab instead
      photos: [
        { key: 'PHOTO_INTERVAL_S', label: 'Photo Interval (s)', hint: 'z.B. 300 = alle 5 Minuten', type: 'number' },
        { key: 'TIMELAPSE_FPS', label: 'Timelapse FPS', hint: 'z.B. 25', type: 'number' },
        { key: 'TIMELAPSE_DAYS', label: 'Timelapse Span (days)', hint: 'z.B. 1 = täglich', type: 'number' },
      ],
      upload: [
        { key: 'HIDRIVE_USER', label: 'HiDrive Benutzername', hint: 'Strato HiDrive Benutzername', type: 'text' },
        { key: 'HIDRIVE_PASSWORD', label: 'HiDrive Passwort', hint: 'Strato HiDrive Passwort', type: 'password' },
        { key: 'HIDRIVE_TARGET_DIR', label: 'HiDrive Zielverzeichnis', hint: 'z.B. Birdshome', type: 'text' },
        { key: 'UPLOAD_PHOTOS', label: 'Fotos hochladen', hint: 'Snapshots zu HiDrive hochladen', type: 'toggle' },
        { key: 'UPLOAD_VIDEOS', label: 'Videos hochladen', hint: 'Motion-Videos zu HiDrive hochladen', type: 'toggle' },
        { key: 'UPLOAD_TIMELAPSES', label: 'Timelapses hochladen', hint: 'Timelapse-Videos zu HiDrive hochladen', type: 'toggle' },
        { key: 'UPLOAD_START_HOUR', label: 'Upload Start Stunde', hint: 'Upload startet ab dieser Stunde (0-23, z.B. 22 für 22:00)', type: 'number' },
        { key: 'UPLOAD_END_HOUR', label: 'Upload Ende Stunde', hint: 'Upload endet vor dieser Stunde (0-23, z.B. 6 für 6:00)', type: 'number' },
        { key: 'UPLOAD_INTERVAL_MIN', label: 'Upload Interval (min)', hint: 'z.B. 30', type: 'number' },
        { key: 'RETENTION_DAYS', label: 'Retention Days', hint: 'z.B. 14', type: 'number' },
        { key: 'UPLOAD_RETENTION_DAYS', label: 'Upload Retention Days', hint: 'Hochgeladene Dateien nach N Tagen löschen (z.B. 30)', type: 'number' },
      ],
      ai: [
        { key: 'YOLO_MODEL_PATH', label: 'YOLO Model Path', hint: 'Pfad zum Modell auf dem Gerät', type: 'text' },
        { key: 'YOLO_THRESH', label: 'YOLO Threshold', hint: '0.0–1.0', type: 'text' },
        { key: 'DETECTION_START_HOUR', label: 'Erkennung Start Stunde', hint: 'KI-Erkennung startet ab dieser Stunde (0-23, z.B. 14 für 14:00)', type: 'number' },
        { key: 'DETECTION_END_HOUR', label: 'Erkennung Ende Stunde', hint: 'KI-Erkennung endet vor dieser Stunde (0-23, z.B. 6 für 6:00)', type: 'number' },
      ],
      ir: [
        { key: 'IR_GPIO', label: 'IR GPIO', hint: 'GPIO Pin Nummer (BCM)', type: 'number' },
        { key: 'LUX_GPIO', label: 'LUX GPIO', hint: 'GPIO Pin Nummer (BCM)', type: 'number' },
        { key: 'LUX_THRESHOLD', label: 'LUX Threshold', hint: 'z.B. 0.5', type: 'text' },
      ],
      system: [
        { key: 'LOG_ENABLED', label: 'Logging Enabled', hint: '0 oder 1', type: 'toggle' },
        {
          key: 'LOG_LEVEL',
          label: 'Log Level',
          hint: 'DEBUG | INFO | WARNING | ERROR',
          type: 'select',
          options: [
            { label: 'DEBUG', value: 'DEBUG' },
            { label: 'INFO', value: 'INFO' },
            { label: 'WARNING', value: 'WARNING' },
            { label: 'ERROR', value: 'ERROR' },
          ],
        },
        { key: 'WIFI_SSID', label: 'WiFi SSID', hint: 'WLAN-Netzwerkname für Fallback', type: 'text' },
        { key: 'WIFI_PASSWORD', label: 'WiFi Passwort', hint: 'WLAN-Passwort für Fallback', type: 'password' },
      ],
    }),
    []
  );

  const renderContent = () => {
    switch (activeTab) {
      case 'health':
        return <HealthPage />;
      case 'logs':
        return <LogsPage />;
      case 'video':
        return (
          <>
            <MotionControl />
            <div className="mt-6">
              <GroupedSettingsPanel
                title={tabs.find((t) => t.id === activeTab)?.label || 'Settings'}
                groups={fieldGroupsByTab[activeTab] || []}
                settings={settings}
                setSettings={setSettings}
                loaded={settingsLoaded}
                onSave={save}
                saveState={saveState}
                saveError={saveError}
              />
            </div>
          </>
        );
      default:
        return (
          <SettingsPanel
            title={tabs.find((t) => t.id === activeTab)?.label || 'Settings'}
            fields={fieldsByTab[activeTab] || []}
            settings={settings}
            setSettings={setSettings}
            loaded={settingsLoaded}
            onSave={save}
            saveState={saveState}
            saveError={saveError}
          />
        );
    }
  };

  return (
    <div>
      <h2 className="text-3xl font-bold text-gray-800 dark:text-white mb-6">Admin Panel</h2>
      <div className="flex space-x-1 border-b border-gray-300 dark:border-gray-600 mb-6 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center space-x-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === tab.id
                ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            {React.cloneElement(tab.icon, { size: 18 })}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>
      <div>{renderContent()}</div>
    </div>
  );
};

const SettingsPanel: React.FC<{
  title: string;
  fields: FieldDef[];
  settings: Record<string, string>;
  setSettings: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  loaded: boolean;
  onSave: () => void;
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  saveError: string | null;
}> = ({ title, fields, settings, setSettings, loaded, onSave, saveState, saveError }) => {
  const setValue = (key: string, value: string) => setSettings((s) => ({ ...s, [key]: value }));

  const renderField = (f: FieldDef) => {
    const value = settings[f.key] || '';

    const commonClass =
      'md:col-span-2 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-800 dark:text-white';

    const labelBlock = (
      <div>
        <div className="text-sm font-medium text-gray-800 dark:text-gray-100">{f.label}</div>
        {f.hint && <div className="text-xs text-gray-500 dark:text-gray-400">{f.hint}</div>}
      </div>
    );

    let control: React.ReactNode;
    switch (f.type) {
      case 'select':
        control = (
          <select value={value} onChange={(e) => setValue(f.key, e.target.value)} className={commonClass}>
            {(f.options || []).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        );
        break;
      case 'toggle': {
        const checked = value === '1' || value.toLowerCase?.() === 'true';
        control = (
          <label className="md:col-span-2 inline-flex items-center gap-3 select-none">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setValue(f.key, e.target.checked ? '1' : '0')}
              className="h-4 w-4 rounded border-gray-300 dark:border-gray-700"
            />
            <span className="text-sm text-gray-700 dark:text-gray-200">{checked ? 'Enabled' : 'Disabled'}</span>
          </label>
        );
        break;
      }
      case 'number':
        control = (
          <input
            type="number"
            value={value}
            onChange={(e) => setValue(f.key, e.target.value)}
            className={commonClass}
          />
        );
        break;
      case 'password':
        control = (
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(f.key, e.target.value)}
            className={commonClass}
            placeholder="••••••••"
          />
        );
        break;
      case 'text':
      default:
        control = (
          <input value={value} onChange={(e) => setValue(f.key, e.target.value)} className={commonClass} />
        );
        break;
    }

    return (
      <div key={f.key} className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
        {labelBlock}
        {control}
      </div>
    );
  };

  return (
    <div className="bg-white dark:bg-gray-800 p-8 rounded-lg shadow-md">
      <div className="flex items-center justify-between gap-4 mb-6">
        <div>
          <h3 className="text-xl font-bold text-gray-800 dark:text-white">{title}</h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">Persistiert in SQLite (Settings-Tabelle).</p>
        </div>
        <button
          onClick={onSave}
          disabled={!loaded || saveState === 'saving'}
          className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 px-4 rounded-lg transition-colors disabled:opacity-70 flex items-center"
        >
          <Save size={16} className="mr-2" />
          {saveState === 'saving' ? 'Saving...' : saveState === 'saved' ? 'Saved' : saveState === 'error' ? 'Error' : 'Save Changes'}
        </button>
      </div>

      {saveError && (
        <div className="mb-4 flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
          <AlertCircle size={16} />
          {saveError}
        </div>
      )}

      {!loaded ? (
        <div className="text-gray-600 dark:text-gray-400">Settings not loaded.</div>
      ) : (
        <div className="space-y-5">
          {fields.length === 0 ? (
            <div className="text-sm text-gray-600 dark:text-gray-400">No configurable settings in this section.</div>
          ) : (
            fields.map(renderField)
          )}
        </div>
      )}
    </div>
  );
};

const GroupedSettingsPanel: React.FC<{
  title: string;
  groups: FieldGroup[];
  settings: Record<string, string>;
  setSettings: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  loaded: boolean;
  onSave: () => void;
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  saveError: string | null;
}> = ({ title, groups, settings, setSettings, loaded, onSave, saveState, saveError }) => {
  const setValue = (key: string, value: string) => setSettings((s) => ({ ...s, [key]: value }));

  const renderField = (f: FieldDef) => {
    const value = settings[f.key] || '';

    const commonClass =
      'md:col-span-2 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-800 dark:text-white';

    const labelBlock = (
      <div>
        <div className="text-sm font-medium text-gray-800 dark:text-gray-100">{f.label}</div>
        {f.hint && <div className="text-xs text-gray-500 dark:text-gray-400">{f.hint}</div>}
      </div>
    );

    let control: React.ReactNode;
    switch (f.type) {
      case 'select':
        control = (
          <select value={value} onChange={(e) => setValue(f.key, e.target.value)} className={commonClass}>
            {(f.options || []).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        );
        break;
      case 'toggle': {
        const checked = value === '1' || value.toLowerCase?.() === 'true';
        control = (
          <label className="md:col-span-2 inline-flex items-center gap-3 select-none">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setValue(f.key, e.target.checked ? '1' : '0')}
              className="h-4 w-4 rounded border-gray-300 dark:border-gray-700"
            />
            <span className="text-sm text-gray-700 dark:text-gray-200">{checked ? 'Enabled' : 'Disabled'}</span>
          </label>
        );
        break;
      }
      case 'number':
        control = (
          <input
            type="number"
            value={value}
            onChange={(e) => setValue(f.key, e.target.value)}
            className={commonClass}
          />
        );
        break;
      case 'password':
        control = (
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(f.key, e.target.value)}
            className={commonClass}
            placeholder="••••••••"
          />
        );
        break;
      case 'text':
      default:
        control = (
          <input value={value} onChange={(e) => setValue(f.key, e.target.value)} className={commonClass} />
        );
        break;
    }

    return (
      <div key={f.key} className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
        {labelBlock}
        {control}
      </div>
    );
  };

  return (
    <div className="bg-white dark:bg-gray-800 p-8 rounded-lg shadow-md">
      <div className="flex items-center justify-between gap-4 mb-6">
        <div>
          <h3 className="text-xl font-bold text-gray-800 dark:text-white">{title}</h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">Persistiert in SQLite (Settings-Tabelle).</p>
        </div>
        <button
          onClick={onSave}
          disabled={!loaded || saveState === 'saving'}
          className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 px-4 rounded-lg transition-colors disabled:opacity-70 flex items-center"
        >
          <Save size={16} className="mr-2" />
          {saveState === 'saving' ? 'Saving...' : saveState === 'saved' ? 'Saved' : saveState === 'error' ? 'Error' : 'Save Changes'}
        </button>
      </div>

      {saveError && (
        <div className="mb-4 flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
          <AlertCircle size={16} />
          {saveError}
        </div>
      )}

      {!loaded ? (
        <div className="text-gray-600 dark:text-gray-400">Settings not loaded.</div>
      ) : (
        <div className="space-y-8">
          {groups.length === 0 ? (
            <div className="text-sm text-gray-600 dark:text-gray-400">No configurable settings in this section.</div>
          ) : (
            groups.map((group, idx) => (
              <div key={idx} className="border-t border-gray-200 dark:border-gray-700 pt-6 first:border-t-0 first:pt-0">
                <div className="mb-4">
                  <h4 className="text-lg font-semibold text-gray-800 dark:text-white">{group.title}</h4>
                  {group.description && (
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{group.description}</p>
                  )}
                </div>
                <div className="space-y-5">
                  {group.fields.map(renderField)}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default AdminPage;
