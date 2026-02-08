import React from 'react';

interface ToggleSwitchProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
  loading?: boolean;
}

export const ToggleSwitch: React.FC<ToggleSwitchProps> = ({ enabled, onChange, disabled, loading }) => {
  return (
    <button
      type="button"
      onClick={() => !disabled && !loading && onChange(!enabled)}
      disabled={disabled || loading}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed ${
        enabled ? 'bg-emerald-600' : 'bg-gray-200 dark:bg-gray-700'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          enabled ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );
};
