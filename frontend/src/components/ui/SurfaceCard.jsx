const VARIANTS = {
  default: 'rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card',
  filter: 'rounded-2xl border border-slate-200/80 bg-white p-4 shadow-card',
  panel: 'rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card',
  flat: 'rounded-2xl border border-slate-200/80 bg-white p-5',
};

export default function SurfaceCard({ children, variant = 'default', className = '', as: Tag = 'div', ...rest }) {
  return (
    <Tag className={`${VARIANTS[variant] || VARIANTS.default} ${className}`} {...rest}>
      {children}
    </Tag>
  );
}
