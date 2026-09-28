'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight } from 'lucide-react';

interface RouteMeta {
  section: string;
  name: string;
}

const ROUTE_MAP: Record<string, RouteMeta> = {
  '/': { section: 'Workspace', name: 'Overview' },
  '/ask': { section: 'Workspace', name: 'Ask AI (NL Query)' },
  '/analysis': { section: 'Workspace', name: 'Analysis Workspace' },
  '/dashboards': { section: 'Workspace', name: 'Executive Dashboard' },
  '/datasets': { section: 'Data', name: 'Datasets Catalog' },
  '/upload': { section: 'Data', name: 'Upload Dataset' },
  '/plan-runner': { section: 'Workflow', name: 'Plan Runner' },
  '/settings': { section: 'System', name: 'Settings' },
};

export const Breadcrumbs: React.FC<{ extra?: string }> = ({ extra }) => {
  const pathname = usePathname();
  const current = ROUTE_MAP[pathname] || { section: 'Platform', name: pathname.replace('/', '') };

  return (
    <nav className="flex items-center text-xs text-muted-foreground font-medium select-none">
      <span className="text-muted-foreground/80">{current.section}</span>
      <ChevronRight className="w-3.5 h-3.5 mx-1.5 text-muted-foreground/60 shrink-0" />
      <span className={extra ? 'text-muted-foreground' : 'text-foreground font-semibold'}>
        {current.name}
      </span>
      {extra && (
        <>
          <ChevronRight className="w-3.5 h-3.5 mx-1.5 text-muted-foreground/60 shrink-0" />
          <span className="text-foreground font-semibold truncate max-w-xs">{extra}</span>
        </>
      )}
    </nav>
  );
};
