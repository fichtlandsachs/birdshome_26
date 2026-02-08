import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import de from './locales/de.json';
import en from './locales/en.json';

// Get language from localStorage or default to German
const getInitialLanguage = (): string => {
  const stored = localStorage.getItem('birdshome_language');
  if (stored && (stored === 'de' || stored === 'en')) {
    return stored;
  }
  // Default to German
  return 'de';
};

i18n
  .use(initReactI18next)
  .init({
    resources: {
      de: { translation: de },
      en: { translation: en },
    },
    lng: getInitialLanguage(),
    fallbackLng: 'de',
    interpolation: {
      escapeValue: false, // React already escapes
    },
  });

// Save language changes to localStorage
i18n.on('languageChanged', (lng) => {
  localStorage.setItem('birdshome_language', lng);
});

export default i18n;
