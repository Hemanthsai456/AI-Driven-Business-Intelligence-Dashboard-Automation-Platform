import React from 'react';

interface LoadingSpinnerProps {
  label?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  label = 'Loading analytics...',
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-12 space-y-3">
      <div className="relative w-8 h-8">
        <div className="w-8 h-8 rounded-full border-2 border-border border-t-primary animate-spin" />
      </div>
      <p className="text-xs font-mono text-muted-foreground animate-pulse">
        {label}
      </p>
    </div>
  );
};
