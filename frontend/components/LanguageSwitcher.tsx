import React from 'react';
import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';

export const LanguageSwitcher: React.FC = () => {
  const { i18n } = useTranslation();

  const toggleLanguage = () => {
    const newLang = i18n.language === 'de' ? 'en' : 'de';
    i18n.changeLanguage(newLang);
  };

  return (
    <button
      onClick={toggleLanguage}
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
      title={i18n.language === 'de' ? 'Switch to English' : 'Zu Deutsch wechseln'}
    >
      <Globe size={18} className="text-gray-600 dark:text-gray-300" />
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300 uppercase">
        {i18n.language}
      </span>
    </button>
  );
};
