import React from 'react';
import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

export const ThemeToggle: React.FC = () => {
  const { theme, setTheme } = useTheme();

  const themes = [
    { value: 'light' as const, icon: Sun, label: 'Hell' },
    { value: 'dark' as const, icon: Moon, label: 'Dunkel' },
    { value: 'system' as const, icon: Monitor, label: 'System' },
  ];

  return (
    <div className="flex items-center gap-1 p-1 bg-gray-200 dark:bg-gray-700 rounded-lg">
      {themes.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          className={`p-2 rounded transition-colors ${
            theme === value
              ? 'bg-white dark:bg-gray-600 text-emerald-600 dark:text-emerald-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
          }`}
          title={label}
        >
          <Icon size={18} />
        </button>
      ))}
    </div>
  );
};
