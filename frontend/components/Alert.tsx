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
      bg: 'bg-[#FFEBEE] border-[#FFCDD2] text-[#C62828] dark:bg-[#40181A] dark:border-[#C62828]/50 dark:text-[#EF9A9A]',
      icon: <AlertCircle className="w-4 h-4 text-[#C62828] shrink-0 mt-0.5" />,
    },
    warning: {
      bg: 'bg-[#FFF8E1] border-[#FFE082] text-[#9A6700] dark:bg-[#3D2E14] dark:border-[#F2B22E]/40 dark:text-[#F2B22E]',
      icon: <AlertTriangle className="w-4 h-4 text-[#F2B22E] shrink-0 mt-0.5" />,
    },
    success: {
      bg: 'bg-[#E8F5E9] border-[#C8E6C9] text-[#2E7D32] dark:bg-[#1B3E20] dark:border-[#2E7D32]/50 dark:text-[#A5D6A7]',
      icon: <CheckCircle2 className="w-4 h-4 text-[#2E7D32] shrink-0 mt-0.5" />,
    },
    info: {
      bg: 'bg-[#E6D4B8]/40 border-[#DAC7AD] text-[#212121] dark:bg-[#2A2A2A] dark:border-[#3A3530] dark:text-[#F5EBE1]',
      icon: <Info className="w-4 h-4 text-[#EA6928] shrink-0 mt-0.5" />,
    },
  };

  const current = styles[variant];

  return (
    <div className={`p-3 border rounded flex items-start gap-2.5 text-xs ${current.bg}`}>
      {current.icon}
      <div className="min-w-0">
        {title && <h4 className="font-semibold leading-tight">{title}</h4>}
        <p className="mt-0.5 opacity-90 leading-relaxed text-2xs">{message}</p>
      </div>
    </div>
  );
};
