import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen bg-surface-muted">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
      <main
        className={`min-h-screen transition-all duration-300 p-6 lg:p-8 ${collapsed ? 'ml-[72px]' : 'ml-64'}`}
      >
        <Outlet />
      </main>
    </div>
  );
}
