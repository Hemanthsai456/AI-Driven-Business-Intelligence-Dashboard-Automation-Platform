/**
 * Centralized Design System Tokens for Stage 4b (Item 10)
 *
 * Strict single source of truth for color palette, borders, radius, and chart colors.
 * Components must consume these tokens or corresponding CSS variables/tailwind classes.
 */

export const THEME_TOKENS = {
  // Surfaces & Background
  background: '#F7F8FA',
  surface: '#FFFFFF',
  border: '#E3E7EC',

  // Typography
  text: '#1F2A37',
  mutedText: '#6B7785',

  // Primary (Muted Teal)
  primary: '#2F7F7A',
  primaryHover: '#276A66',
  primarySoft: '#E6F1F0',

  // Attention (Amber)
  attention: '#C98A2B',
  attentionSoft: '#FBF3E4',

  // Feedback (Muted)
  error: '#B4534B',
  errorSoft: '#FDF2F2',
  success: '#4C8B6B',
  successSoft: '#F0FDF4',

  // Chart Series in mandatory sequence
  chartSeries: [
    '#2F7F7A', // Teal
    '#5B7C99', // Slate Blue
    '#C9A66B', // Muted Gold
    '#B56576', // Rose
    '#9AA5B1', // Cool Grey
  ] as const,

  // Geometry
  borderRadiusCard: '10px',
  borderWidth: '1px',
} as const;

export type ThemeTokens = typeof THEME_TOKENS;

export const DARK_THEME_TOKENS = {
  // Surfaces & Background
  background: '#12171C',
  surface: '#1A2128',
  border: '#2A333C',

  // Typography
  text: '#E6EAEE',
  mutedText: '#98A3AF',

  // Primary (Luminous Teal)
  primary: '#4FA39D',
  primaryHover: '#5BB3AD',
  primarySoft: '#1E3533',

  // Attention (Amber)
  attention: '#D9A441',
  attentionSoft: '#33291A',

  // Feedback
  error: '#D96B62',
  errorSoft: '#2E1A18',
  success: '#4EA37E',
  successSoft: '#162B21',

  // Chart Series (Dark Mode: Optimized for contrast on dark surfaces)
  chartSeries: [
    '#4FA39D', // Teal
    '#7AA2C0', // Slate Blue
    '#E0BA7E', // Muted Gold
    '#D97387', // Rose
    '#B0BAC5', // Cool Silver/Grey
  ] as const,

  // Geometry
  borderRadiusCard: '10px',
  borderWidth: '1px',
} as const;

export { useChartTheme, getChartTokens } from './chartTheme';


