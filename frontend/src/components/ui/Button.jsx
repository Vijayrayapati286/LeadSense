import { Link } from 'react-router-dom';
import LoadingSpinner from './LoadingSpinner';

const VARIANTS = {
  primary:
    'bg-primary-600 text-white shadow-button hover:bg-primary-700 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary-500/20',
  secondary:
    'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 hover:border-slate-400 hover:shadow-sm',
  ghost: 'bg-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-700',
  danger: 'bg-red-600 text-white hover:bg-red-700',
};

const SIZES = {
  sm: 'px-3 py-1.5 text-xs rounded-lg gap-1',
  md: 'px-4 py-2.5 text-sm rounded-xl gap-2',
  lg: 'px-5 py-3 text-sm rounded-xl gap-2',
};

const BASE =
  'inline-flex items-center justify-center font-semibold transition-all duration-200 active:scale-[.98] focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-none';

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  icon: Icon,
  iconPosition = 'left',
  loading = false,
  disabled = false,
  to,
  type = 'button',
  className = '',
  onClick,
  ...rest
}) {
  const classes = `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`;
  const iconEl = loading ? (
    <LoadingSpinner size="sm" />
  ) : Icon ? (
    <Icon size={size === 'sm' ? 13 : 15} className="shrink-0" />
  ) : null;

  const content = (
    <>
      {iconPosition === 'left' && iconEl}
      {children}
      {iconPosition === 'right' && iconEl}
    </>
  );

  if (to) {
    return (
      <Link to={to} className={classes} {...rest}>
        {content}
      </Link>
    );
  }

  return (
    <button type={type} className={classes} disabled={disabled || loading} onClick={onClick} {...rest}>
      {content}
    </button>
  );
}
