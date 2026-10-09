'use client';

import React from 'react';
import { useTheme } from '../components/ThemeProvider';
import { THEME_TOKENS, DARK_THEME_TOKENS } from './theme';

export interface ChartThemeTokens {
  surface: string;
  surfaceElevated: string;
  surfaceMuted: string;
  border: string;
  borderStrong: string;
  text: string;
  mutedText: string;
  primary: string;
  series: readonly string[];
}

/**
 * Returns static token hex values for the specified theme.
 */
export function getChartTokens(resolvedTheme: 'light' | 'dark' = 'light'): ChartThemeTokens {
  const isDark = resolvedTheme === 'dark';
  const tokens = isDark ? DARK_THEME_TOKENS : THEME_TOKENS;
  return {
    surface: tokens.surface,
    surfaceElevated: isDark ? '#222B34' : '#FFFFFF',
    surfaceMuted: isDark ? '#242D36' : '#F0F2F5',
    border: tokens.border,
    borderStrong: isDark ? '#3A4652' : '#CBD2D9',
    text: tokens.text,
    mutedText: tokens.mutedText,
    primary: tokens.primary,
    series: tokens.chartSeries,
  };
}

/**
 * Hook providing centralized, theme-aware styling and configuration for Recharts.
 * Automatically adapts all chart elements (grid, axes, ticks, tooltips, series)
 * to light and dark modes, reacting immediately to theme switches.
 */
export function useChartTheme() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const tokens = getChartTokens(resolvedTheme);

  // CartesianGrid props adapting to active theme border token
  const gridProps = React.useMemo(() => ({
    stroke: 'var(--border)',
    strokeDasharray: '3 3',
    opacity: isDark ? 0.35 : 0.6,
  }), [isDark]);

  // XAxis props adapting to active theme border stroke and muted-foreground ticks
  const xAxisProps = React.useCallback((overrides: Record<string, any> = {}) => ({
    stroke: 'var(--border)',
    tickLine: { stroke: 'var(--border)' },
    tick: { fontSize: 10, fill: 'var(--muted-foreground)' },
    ...overrides,
  }), []);

  // YAxis props adapting to active theme border stroke and muted-foreground ticks
  const yAxisProps = React.useCallback((overrides: Record<string, any> = {}) => ({
    stroke: 'var(--border)',
    tickLine: { stroke: 'var(--border)' },
    tick: { fontSize: 10, fill: 'var(--muted-foreground)' },
    ...overrides,
  }), []);

  // Tooltip props adapting to active theme surface background, border, and text
  const tooltipProps = React.useMemo(() => ({
    contentStyle: {
      backgroundColor: 'var(--surface)',
      borderColor: 'var(--border)',
      borderWidth: '1px',
      borderStyle: 'solid',
      borderRadius: '8px',
      boxShadow: isDark
        ? '0 6px 18px rgba(0, 0, 0, 0.45)'
        : '0 4px 14px rgba(0, 0, 0, 0.08)',
      fontSize: '11px',
      color: 'var(--foreground)',
      padding: '8px 12px',
    },
    itemStyle: {
      color: 'var(--foreground)',
      fontSize: '11px',
      padding: '2px 0',
    },
    labelStyle: {
      color: 'var(--foreground)',
      fontWeight: 600,
      fontSize: '11px',
      marginBottom: '4px',
    },
    cursor: {
      fill: isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.04)',
      stroke: 'var(--border)',
      strokeDasharray: '3 3',
    },
  }), [isDark]);

  // Legend props adapting to active theme text
  const legendProps = React.useMemo(() => ({
    wrapperStyle: {
      fontSize: '11px',
      color: 'var(--foreground)',
      paddingTop: '8px',
    },
  }), []);

  return {
    theme: resolvedTheme,
    isDark,
    themeKey: resolvedTheme,
    tokens,
    gridProps,
    xAxisProps,
    yAxisProps,
    tooltipProps,
    legendProps,
    containerClass: 'bg-surface border border-border rounded-lg p-3',
  };
}
