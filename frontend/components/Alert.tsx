import React from 'react';
import { AlertTriangle, AlertCircle, CheckCircle2, Info } from 'lucide-react';

export interface AlertProps {
  title?: string;
  message: string;
  variant?: 'error' | 'warning' | 'success' | 'info';
}

export const Alert: React.FC<AlertProps> = ({
  title,
  message,
  variant = 'info',
}) => {
  const styles = {
    error: {
      bg: 'bg-rose-500/10 border-rose-500/20 text-rose-800 dark:text-rose-200',
      icon: <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />,
    },
    warning: {
      bg: 'bg-amber-500/10 border-amber-500/20 text-amber-800 dark:text-amber-200',
      icon: <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />,
    },
    success: {
      bg: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-800 dark:text-emerald-200',
      icon: <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />,
    },
    info: {
      bg: 'bg-primary/10 border-primary/20 text-foreground',
      icon: <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />,
    },
  };

  const current = styles[variant];

  return (
    <div className={`p-3.5 border rounded-lg flex items-start gap-2.5 text-xs ${current.bg}`}>
      {current.icon}
      <div className="min-w-0">
        {title && <h4 className="font-semibold text-foreground">{title}</h4>}
        <p className="mt-0.5 opacity-90 leading-relaxed">{message}</p>
      </div>
    </div>
  );
};
