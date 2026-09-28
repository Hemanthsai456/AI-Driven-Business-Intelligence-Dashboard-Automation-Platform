import './globals.css';
import React from 'react';
import { ThemeProvider } from '../components/ThemeProvider';
import { AppShell } from '../components/AppShell';

export const metadata = {
  title: 'AI BI & Dashboard Automation Platform',
  description: 'Turn raw datasets into explainable analytical understanding and interactive dashboards.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-background text-foreground min-h-screen">
        <ThemeProvider>
          <AppShell>
            {children}
          </AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
