import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'blue' | 'purple' | 'green' | 'amber' | 'slate' | 'red';
  size?: 'xs' | 'sm' | 'md';
  dot?: boolean;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'slate',
  size = 'sm',
  dot = false,
  className = '',
}) => {
  const variantStyles = {
    blue: 'bg-[#E6D4B8] text-[#212121] border-[#DAC7AD] dark:bg-[#2A2A2A] dark:text-[#F5EBE1] dark:border-[#3A3530]',
    purple: 'bg-[#F5EDF8] text-[#6B21A8] border-[#E9D5FF] dark:bg-[#3B1F4D] dark:text-[#E9D5FF] dark:border-[#581C87]',
    green: 'bg-[#E8F5E9] text-[#2E7D32] border-[#C8E6C9] dark:bg-[#1B3E20] dark:text-[#A5D6A7] dark:border-[#2E7D32]',
    amber: 'bg-[#FFF8E1] text-[#9A6700] border-[#FFE082] dark:bg-[#3D2E14] dark:text-[#F2B22E] dark:border-[#F2B22E]/40',
    slate: 'bg-[#F2E8DC] text-[#6B6055] border-[#DAC7AD] dark:bg-[#2A2A2A] dark:text-[#A89D91] dark:border-[#3A3530]',
    red: 'bg-[#FFEBEE] text-[#C62828] border-[#FFCDD2] dark:bg-[#40181A] dark:text-[#EF9A9A] dark:border-[#C62828]',
  };

  const dotColors = {
    blue: 'bg-[#EA6928]',
    purple: 'bg-[#9333EA]',
    green: 'bg-[#2E7D32]',
    amber: 'bg-[#F2B22E]',
    slate: 'bg-[#6B6055]',
    red: 'bg-[#C62828]',
  };

  const sizeStyles = {
    xs: 'px-1.5 py-0.5 text-2xs gap-1 font-medium',
    sm: 'px-2 py-0.5 text-xs gap-1 font-medium',
    md: 'px-2.5 py-1 text-xs gap-1.5 font-semibold',
  };

  return (
    <span
      className={`inline-flex items-center rounded border tracking-wide uppercase font-mono ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${dotColors[variant]}`} />}
      {children}
    </span>
  );
};
