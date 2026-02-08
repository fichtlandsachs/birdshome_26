import React, { useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { api } from '../../lib/api';

type LoginPageProps = {
  onLoggedIn: () => void;
  /**
   * "full" renders as a dedicated page.
   * "panel" renders as an in-app panel (e.g. within the admin area).
   */
  mode?: 'full' | 'panel';
  onCancel?: () => void;
};

const LoginPage: React.FC<LoginPageProps> = ({ onLoggedIn, mode = 'full', onCancel }) => {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
      try {
          const res = await api.login(username, password);
          // Wenn der Login erfolgreich war, leiten wir weiter
          if (res) {
              console.log("Login erfolgreich, leite weiter...");
              navigate('/'); // Zur Startseite/Dashboard
          }
      } catch (err: any) {
          setError(err.message || 'Login fehlgeschlagen');
      }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.login(username, password);
      onLoggedIn();
    } catch (err: any) {
      setError(err?.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const containerClass =
    mode === 'panel'
      ? 'flex items-center justify-center bg-transparent p-6'
      : 'min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 p-6';

  return (
    <div className={containerClass}>
      <div className="w-full max-w-md bg-white dark:bg-gray-800 rounded-lg shadow-md p-8">
        <div className="flex items-center mb-6">
          <ShieldCheck className="text-emerald-500" size={32} />
          <h1 className="ml-2 text-2xl font-bold text-gray-800 dark:text-white">Birdshome</h1>
        </div>
        <h2 className="text-xl font-semibold text-gray-800 dark:text-white mb-2">Sign in</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">Admin access required.</p>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-800 dark:text-white"
              autoComplete="username"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-800 dark:text-white"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-300 p-3 rounded-lg">
              {error}
            </div>
          )}

          <button
            disabled={loading}
            type="submit"
            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 px-4 rounded-lg transition-colors disabled:opacity-70"
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>

          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="w-full bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-100 font-semibold py-2 px-4 rounded-lg transition-colors"
            >
              Cancel
            </button>
          )}
        </form>

        <p className="mt-6 text-xs text-gray-500 dark:text-gray-400">
          Tipp: Setze ADMIN_USERNAME/ADMIN_PASSWORD in backend/.env
        </p>
      </div>
    </div>
  );
};

export default LoginPage;
