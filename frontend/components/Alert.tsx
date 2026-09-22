import React from 'react';
import { AlertTriangle, AlertCircle, CheckCircle2, Info } from 'lucide-react';

interface AlertProps {
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
      bg: 'bg-rose-500/10 border-rose-500/20 text-rose-200',
      icon: <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />,
    },
    warning: {
      bg: 'bg-amber-500/10 border-amber-500/20 text-amber-200',
      icon: <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />,
    },
    success: {
      bg: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-200',
      icon: <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />,
    },
    info: {
      bg: 'bg-sky-500/10 border-sky-500/20 text-sky-200',
      icon: <Info className="w-5 h-5 text-sky-400 flex-shrink-0 mt-0.5" />,
    },
  };

  const current = styles[variant];

  return (
    <div className={`p-4 border rounded-xl flex items-start space-x-3 text-sm ${current.bg}`}>
      {current.icon}
      <div>
        {title && <h4 className="font-semibold">{title}</h4>}
        <p className="text-xs mt-0.5 opacity-90">{message}</p>
      </div>
    </div>
  );
};
