import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'blue' | 'purple' | 'green' | 'amber' | 'slate' | 'red' | 'teal';
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
    teal: 'bg-[#E6F1F0] text-[#2F7F7A] border-[#2F7F7A]/25',
    blue: 'bg-[#EBF1F5] text-[#5B7C99] border-[#5B7C99]/25',
    purple: 'bg-[#F4EFF7] text-[#7B5B99] border-[#7B5B99]/25',
    green: 'bg-[#F0FDF4] text-[#4C8B6B] border-[#4C8B6B]/25',
    amber: 'bg-[#FBF3E4] text-[#C98A2B] border-[#C98A2B]/30',
    slate: 'bg-[#F0F2F5] text-[#6B7785] border-[#E3E7EC]',
    red: 'bg-[#FDF2F2] text-[#B4534B] border-[#B4534B]/25',
  };

  const dotColors = {
    teal: 'bg-[#2F7F7A]',
    blue: 'bg-[#5B7C99]',
    purple: 'bg-[#7B5B99]',
    green: 'bg-[#4C8B6B]',
    amber: 'bg-[#C98A2B]',
    slate: 'bg-[#6B7785]',
    red: 'bg-[#B4534B]',
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
