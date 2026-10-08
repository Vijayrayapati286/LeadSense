import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const sidebarOffset = collapsed ? '72px' : '16rem';

  useEffect(() => {
    document.documentElement.style.setProperty('--app-sidebar', sidebarOffset);
    return () => document.documentElement.style.removeProperty('--app-sidebar');
  }, [sidebarOffset]);

  return (
    <div className="min-h-screen bg-surface-muted" style={{ '--app-sidebar': sidebarOffset }}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
      <main
        className={`min-h-screen transition-all duration-300 p-6 lg:p-8 ${collapsed ? 'ml-[72px]' : 'ml-64'}`}
      >
        <Outlet />
      </main>
    </div>
  );
}
