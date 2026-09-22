import './globals.css';
import React from 'react';
import { Sidebar } from '../components/Sidebar';

export const metadata = {
  title: 'AI BI & Dashboard Automation Platform',
  description: 'Turn raw datasets into explainable analytical understanding and interactive dashboards.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 flex min-h-screen">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
