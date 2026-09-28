import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive' | 'outline' | 'icon';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles =
    'inline-flex items-center justify-center font-medium transition-all select-none rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-[#EA6928]/50 disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98]';

  const variantStyles = {
    primary:
      'bg-[#EA6928] hover:bg-[#D3581B] text-white shadow-xs font-semibold',
    secondary:
      'bg-white dark:bg-[#2A2A2A] hover:bg-[#E6D4B8]/40 dark:hover:bg-[#333333] text-[#212121] dark:text-[#F5EBE1] border border-[#212121]/30 dark:border-[#4F4842]',
    ghost:
      'bg-transparent hover:bg-[#E6D4B8]/40 dark:hover:bg-[#2A2A2A] text-[#212121] dark:text-[#F5EBE1]',
    outline:
      'bg-transparent hover:bg-white/60 dark:hover:bg-[#2A2A2A] border border-[#DAC7AD] dark:border-[#3A3530] text-[#212121] dark:text-[#F5EBE1]',
    destructive:
      'bg-[#C62828] hover:bg-[#B71C1C] text-white shadow-xs',
    icon:
      'bg-transparent hover:bg-[#E6D4B8]/40 dark:hover:bg-[#2A2A2A] text-[#6B6055] hover:text-[#212121] dark:hover:text-[#F5EBE1] p-1.5 rounded',
  };

  const sizeStyles = {
    xs: 'px-2 py-1 text-2xs gap-1 h-6',
    sm: 'px-2.5 py-1.5 text-xs gap-1.5 h-8',
    md: 'px-3.5 py-2 text-xs font-semibold gap-2 h-9',
    lg: 'px-5 py-2.5 text-sm font-semibold gap-2.5 h-10',
  };

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${variant === 'icon' ? '' : sizeStyles[size]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <svg
          className="animate-spin h-3.5 w-3.5 text-current shrink-0"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="3"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      ) : (
        leftIcon && <span className="shrink-0">{leftIcon}</span>
      )}
      {children}
      {!isLoading && rightIcon && <span className="shrink-0">{rightIcon}</span>}
    </button>
  );
};
