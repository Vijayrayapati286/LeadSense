import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  FiHome,
  FiMail,
  FiUsers,
  FiFileText,
  FiList,
  FiSettings,
  FiLogOut,
  FiChevronLeft,
  FiChevronRight,
  FiSend,
  FiShield,
} from 'react-icons/fi';
import { useAuth } from '../hooks/useAuth';

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: FiHome },
  { path: '/campaigns', label: 'Campaigns', icon: FiMail },
  { path: '/recipients', label: 'Prospects', icon: FiUsers },
  { path: '/blacklist', label: 'Blacklist', icon: FiShield },
  { path: '/templates', label: 'Mailers', icon: FiFileText },
  { path: '/logs', label: 'Email Logs', icon: FiList },
  { path: '/settings', label: 'Settings', icon: FiSettings },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const { user, logout } = useAuth();

  return (
    <aside
      className={`fixed left-0 top-0 h-full bg-sidebar text-white transition-all duration-300 z-40 flex flex-col ${
        collapsed ? 'w-[72px]' : 'w-64'
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-white/10">
        <div className="w-9 h-9 bg-primary-500 rounded-lg flex items-center justify-center flex-shrink-0">
          <FiSend size={18} />
        </div>
        {!collapsed && (
          <div className="overflow-hidden">
            <h1 className="font-bold text-sm leading-tight">LeadSense</h1>
            <p className="text-xs text-gray-400">Campaign Manager</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
          const isActive = location.pathname.startsWith(path);
          return (
            <Link
              key={path}
              to={path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group ${
                isActive
                  ? 'bg-sidebar-active text-white shadow-lg shadow-primary-500/20'
                  : 'text-gray-300 hover:bg-sidebar-hover hover:text-white'
              }`}
              title={collapsed ? label : undefined}
            >
              <Icon size={20} className="flex-shrink-0" />
              {!collapsed && <span className="text-sm font-medium">{label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* User & Logout */}
      <div className="border-t border-white/10 p-3">
        {!collapsed && user && (
          <div className="px-3 py-2 mb-2">
            <p className="text-sm font-medium truncate">{user.name}</p>
            <p className="text-xs text-gray-400 truncate">{user.email}</p>
            <p className="text-xs text-gray-500 mt-0.5">{user.department}</p>
          </div>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-gray-300 hover:bg-red-500/20 hover:text-red-400 transition-colors"
          title={collapsed ? 'Logout' : undefined}
        >
          <FiLogOut size={20} />
          {!collapsed && <span className="text-sm font-medium">Logout</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 w-6 h-6 bg-white rounded-full shadow-md flex items-center justify-center text-gray-600 hover:text-primary-600 transition-colors"
      >
        {collapsed ? <FiChevronRight size={14} /> : <FiChevronLeft size={14} />}
      </button>
    </aside>
  );
}
