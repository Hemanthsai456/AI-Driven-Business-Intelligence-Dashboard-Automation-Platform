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
    'inline-flex items-center justify-center font-medium transition-all select-none rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98]';

  const variantStyles = {
    primary:
      'bg-primary hover:bg-primary-hover text-primary-foreground shadow-sm shadow-primary/20 border border-primary/30',
    secondary:
      'bg-surface-muted hover:bg-border text-foreground border border-border',
    ghost:
      'bg-transparent hover:bg-surface-muted text-muted-foreground hover:text-foreground',
    outline:
      'bg-transparent hover:bg-surface-muted border border-border hover:border-border-strong text-foreground',
    destructive:
      'bg-danger hover:opacity-90 text-danger-foreground shadow-sm shadow-danger/20 border border-danger/30',
    icon:
      'bg-transparent hover:bg-surface-muted text-muted-foreground hover:text-foreground p-1.5 rounded-md border border-transparent hover:border-border',
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
