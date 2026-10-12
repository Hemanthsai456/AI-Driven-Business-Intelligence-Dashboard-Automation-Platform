'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';
type Density = 'comfortable' | 'compact';

interface ThemeContextType {
  theme: Theme;
  setTheme: (t: Theme) => void;
  resolvedTheme: 'light' | 'dark';
  density: Density;
  setDensity: (d: Density) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  toggleSidebar: () => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: 'light',
  setTheme: () => {},
  resolvedTheme: 'light',
  density: 'comfortable',
  setDensity: () => {},
  sidebarCollapsed: false,
  setSidebarCollapsed: () => {},
  toggleSidebar: () => {},
});

export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>('light');
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>('light');
  const [density, setDensityState] = useState<Density>('comfortable');
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    try {
      const savedTheme = ((localStorage.getItem('dashcrate_theme') || localStorage.getItem('ai_bi_theme')) as Theme) || 'light';
      const savedDensity = ((localStorage.getItem('dashcrate_density') || localStorage.getItem('ai_bi_density')) as Density) || 'comfortable';
      const savedSidebar = (localStorage.getItem('dashcrate_sidebar_collapsed') ?? localStorage.getItem('ai_bi_sidebar_collapsed')) === 'true';

      setThemeState(savedTheme);
      setDensityState(savedDensity);
      setSidebarCollapsed(savedSidebar);
    } catch {
      // Ignore localStorage issues in private mode
    }
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const updateTheme = () => {
      let active: 'light' | 'dark' = 'light';
      if (theme === 'system') {
        active = mediaQuery.matches ? 'dark' : 'light';
      } else {
        active = theme;
      }
      setResolvedTheme(active);

      const root = document.documentElement;
      if (active === 'dark') {
        root.classList.add('dark');
      } else {
        root.classList.remove('dark');
      }

      if (density === 'compact') {
        root.classList.add('compact');
      } else {
        root.classList.remove('compact');
      }
    };

    updateTheme();
    mediaQuery.addEventListener('change', updateTheme);
    return () => mediaQuery.removeEventListener('change', updateTheme);
  }, [theme, density, mounted]);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    try {
      localStorage.setItem('dashcrate_theme', t);
    } catch {}
  };

  const setDensity = (d: Density) => {
    setDensityState(d);
    try {
      localStorage.setItem('dashcrate_density', d);
    } catch {}
  };

  const handleToggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('dashcrate_sidebar_collapsed', String(next));
      } catch {}
      return next;
    });
  };

  return (
    <ThemeContext.Provider
      value={{
        theme,
        setTheme,
        resolvedTheme,
        density,
        setDensity,
        sidebarCollapsed,
        setSidebarCollapsed,
        toggleSidebar: handleToggleSidebar,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
};
