import React, { useEffect, useState, useCallback } from 'react';
import { Home, Video, Image as ImageIcon, Settings, ShieldCheck, LogIn, LogOut, Lock, Menu, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import DashboardPage from './components/pages/DashboardPage';
import StreamPage from './components/pages/StreamPage';
import GalleryPage from './components/pages/GalleryPage';
import AdminPage from './components/pages/AdminPage';
import LoginPage from './components/pages/LoginPage';
import { ThemeToggle } from './components/ThemeToggle';
import { LanguageSwitcher } from './components/LanguageSwitcher';
import { api } from './lib/api';
import './i18n/config';

type Page = 'dashboard' | 'stream' | 'gallery' | 'admin';
type MediaType = 'all' | 'photo' | 'video' | 'timelapse';

const NavItem: React.FC<{ icon: React.ReactNode; label: string; isActive: boolean; onClick: () => void }> = ({ icon, label, isActive, onClick }) => (
  <button
    onClick={onClick}
    aria-current={isActive ? 'page' : undefined}
    aria-label={label}
    className={`flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors duration-200 w-full text-left ${
      isActive
        ? 'bg-emerald-600 text-white'
        : 'text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
    }`}
  >
    <span aria-hidden="true">{icon}</span>
    <span className="ml-3">{label}</span>
  </button>
);

const App: React.FC = () => {
  const { t } = useTranslation();
  const [currentPage, setCurrentPage] = useState<Page>('dashboard');
  const [galleryMediaType, setGalleryMediaType] = useState<MediaType>('all');
  const [isAuthed, setIsAuthed] = useState<boolean | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const me = await api.me();
        setIsAuthed(me.authenticated);
        setUsername(me.username);
      } catch {
        setIsAuthed(false);
      }
    })();
  }, []);

  const onLoggedIn = async () => {
    const me = await api.me();
    setIsAuthed(me.authenticated);
    setUsername(me.username);
  };

  const doLogout = async () => {
    try {
      await api.logout();
    } finally {
      setIsAuthed(false);
      setUsername(null);
    }
  };

  const navigateToGallery = (mediaType: MediaType = 'all') => {
    setGalleryMediaType(mediaType);
    setCurrentPage('gallery');
  };

  const renderPage = useCallback(() => {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage onNavigate={setCurrentPage} onNavigateToGallery={navigateToGallery} />;
      case 'stream':
        return <StreamPage />;
      case 'gallery':
        return <GalleryPage initialMediaType={galleryMediaType} />;
      case 'admin':
        return <AdminPage />;
      default:
        return <DashboardPage onNavigate={setCurrentPage} onNavigateToGallery={navigateToGallery} />;
    }
  }, [currentPage, galleryMediaType]);

  const navItems = [
    { id: 'dashboard', label: t('nav.dashboard'), icon: <Home size={20} /> },
    { id: 'stream', label: t('nav.stream'), icon: <Video size={20} /> },
    { id: 'gallery', label: t('nav.gallery'), icon: <ImageIcon size={20} /> },
    { id: 'admin', label: t('nav.admin'), icon: <Settings size={20} /> },
  ];

  // Auth is required for admin area only. While session status is unknown (null),
  // we treat the user as unauthenticated for gating purposes, but still render the UI.
  const authed = Boolean(isAuthed);

  return (
    <div className="flex h-screen bg-gray-100 dark:bg-gray-900">
      {/* Menu Toggle Button */}
      <button
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        aria-label={isSidebarOpen ? t('nav.closeMenu') || 'Close menu' : t('nav.openMenu') || 'Open menu'}
        aria-expanded={isSidebarOpen}
        aria-controls="sidebar-navigation"
        className="fixed top-4 left-4 z-50 p-2 rounded-lg bg-white dark:bg-gray-800 shadow-lg"
      >
        {isSidebarOpen ? <X size={24} aria-hidden="true" /> : <Menu size={24} aria-hidden="true" />}
      </button>

      {/* Sidebar Overlay (Mobile) */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-30 md:hidden"
          onClick={() => setIsSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        id="sidebar-navigation"
        aria-label="Main navigation"
        className={`fixed md:static inset-y-0 left-0 z-40 w-64 transform transition-transform duration-300 ease-in-out
          ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          flex-shrink-0 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 p-4 flex flex-col justify-between`}
      >
        <div>
          <div className="flex items-center mb-8" role="banner">
            <ShieldCheck className="text-emerald-500" size={32} aria-hidden="true" />
            <div className="ml-2">
              <h1 className="text-2xl font-bold text-gray-800 dark:text-white">Birdshome</h1>
              {authed && username && <p className="text-xs text-gray-500 dark:text-gray-400" aria-label={`Signed in as ${username}`}>Signed in as {username}</p>}
              {!authed && (
                <p className="text-xs text-gray-500 dark:text-gray-400" role="status">
                  Viewing as guest{isAuthed === null ? ' (checking session...)' : ''}
                </p>
              )}
            </div>
          </div>
          <nav className="space-y-2" aria-label="Primary">
            {navItems.map((item) => (
              <NavItem
                key={item.id}
                icon={item.icon}
                label={item.label}
                isActive={currentPage === item.id}
                onClick={() => {
                  if (item.id === 'gallery') {
                    setGalleryMediaType('all');
                  }
                  setCurrentPage(item.id as Page);
                  setIsSidebarOpen(false);
                }}
              />
            ))}
          </nav>
        </div>

        <div className="space-y-3">
          <div className="flex justify-center gap-2">
            <ThemeToggle />
            <LanguageSwitcher />
          </div>
          {authed ? (
            <button
              onClick={doLogout}
              className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-100"
            >
              <LogOut size={16} className="mr-2" /> {t('nav.logout')}
            </button>
          ) : (
            <button
              onClick={() => {
                setCurrentPage('admin');
                setIsSidebarOpen(false);
              }}
              className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              <LogIn size={16} className="mr-2" /> {t('login.title')}
            </button>
          )}
          <div className="text-center text-xs text-gray-500 dark:text-gray-400">
            <p>Raspberry Pi Nestbox Monitor</p>
            <p>&copy; 2026</p>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-4 md:p-8 pt-16 md:pt-8">
          {currentPage === 'admin' && !authed ? (
            <div>
              <div className="mb-4 flex items-center text-sm text-gray-600 dark:text-gray-300">
                <Lock size={16} className="mr-2" /> Adminbereich – Anmeldung erforderlich.
              </div>
              <LoginPage onLoggedIn={onLoggedIn} mode="panel" onCancel={() => setCurrentPage('dashboard')} />
            </div>
          ) : (
            renderPage()
          )}
        </div>
      </main>
    </div>
  );
};

export default App;
