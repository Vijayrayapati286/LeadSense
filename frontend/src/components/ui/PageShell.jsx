export default function PageShell({ children, className = '', maxWidth = 'max-w-[1500px]' }) {
  return (
    <div className={`mx-auto ${maxWidth} space-y-section pb-10 animate-fade-in ${className}`}>
      {children}
    </div>
  );
}
