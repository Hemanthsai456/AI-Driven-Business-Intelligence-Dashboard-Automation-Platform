'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { ChevronRight } from 'lucide-react';

const ROUTE_MAP: Record<string, string> = {
  '/': 'Home',
  '/ask': 'Ask (NL Query)',
  '/upload': 'Upload Dataset',
  '/analysis': 'Analysis Workspace',
  '/plan-runner': 'Plan Runner',
  '/settings': 'Settings',
};

export const Breadcrumbs: React.FC<{ extra?: string }> = ({ extra }) => {
  const pathname = usePathname();
  const current = ROUTE_MAP[pathname] || pathname.replace('/', '');

  return (
    <nav className="flex items-center text-xs text-muted-foreground font-medium select-none font-sans">
      <span>DashCrate</span>
      <ChevronRight className="w-3.5 h-3.5 mx-1 text-muted-foreground/60 shrink-0" />
      <span className={extra ? 'text-muted-foreground' : 'text-foreground font-semibold'}>
        {current}
      </span>
      {extra && (
        <>
          <ChevronRight className="w-3.5 h-3.5 mx-1 text-muted-foreground/60 shrink-0" />
          <span className="text-foreground font-semibold truncate max-w-xs">{extra}</span>
        </>
      )}
    </nav>
  );
};
