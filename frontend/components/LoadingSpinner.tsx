import React from 'react';

interface LoadingSpinnerProps {
  label?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ label = 'Loading dataset analysis...' }) => {
  return (
    <div className="flex flex-col items-center justify-center p-12 space-y-4">
      <div className="relative w-12 h-12">
        <div className="w-12 h-12 rounded-full border-4 border-slate-800 border-t-sky-500 animate-spin" />
      </div>
      <p className="text-sm font-medium text-slate-400 font-mono animate-pulse">{label}</p>
    </div>
  );
};
