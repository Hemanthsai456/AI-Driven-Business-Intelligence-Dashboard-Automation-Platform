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
