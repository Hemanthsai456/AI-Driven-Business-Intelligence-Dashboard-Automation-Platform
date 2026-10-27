'use client';

import React, { useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

function AnalysisRedirectContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const id = searchParams.get('id');
    const tab = searchParams.get('tab');
    const params = new URLSearchParams();

    if (id) {
      params.set('id', id);
    }

    if (tab) {
      if (tab === 'preview') {
        params.set('tab', 'overview');
      } else if (tab === 'profile' || tab === 'semantic') {
        params.set('tab', 'profiling');
      } else {
        params.set('tab', tab);
      }
    }

    const destination = params.toString() ? `/data-studio?${params.toString()}` : '/data-studio';
    router.replace(destination);
  }, [router, searchParams]);

  return (
    <div className="flex flex-col items-center justify-center p-16 space-y-3">
      <svg className="animate-spin w-6 h-6 text-primary" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
      <span className="text-xs font-mono text-muted-foreground">
        Redirecting to Data Studio...
      </span>
    </div>
  );
}

export default function AnalysisRedirectPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-xs text-muted-foreground font-mono">
          Redirecting to Data Studio...
        </div>
      }
    >
      <AnalysisRedirectContent />
    </Suspense>
  );
}
