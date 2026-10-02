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
      bg: 'bg-error-soft border-error/30 text-error',
      icon: <AlertCircle className="w-4 h-4 text-error shrink-0 mt-0.5" />,
    },
    warning: {
      bg: 'bg-attention-soft border-attention/30 text-attention',
      icon: <AlertTriangle className="w-4 h-4 text-attention shrink-0 mt-0.5" />,
    },
    success: {
      bg: 'bg-success-soft border-success/30 text-success',
      icon: <CheckCircle2 className="w-4 h-4 text-success shrink-0 mt-0.5" />,
    },
    info: {
      bg: 'bg-primary-soft border-primary/30 text-primary',
      icon: <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />,
    },
  };

  const current = styles[variant];

  return (
    <div className={`p-3 border rounded-[10px] flex items-start gap-2.5 text-xs ${current.bg}`}>
      {current.icon}
      <div className="min-w-0">
        {title && <h4 className="font-semibold leading-tight">{title}</h4>}
        <p className="mt-0.5 opacity-90 leading-relaxed text-2xs">{message}</p>
      </div>
    </div>
  );
};
