import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  FiHome,
  FiMail,
  FiFileText,
  FiList,
  FiSettings,
  FiLogOut,
  FiChevronDown,
  FiChevronLeft,
  FiChevronRight,
  FiSend,
  FiShield,
  FiUser,
  FiDatabase,
  FiBriefcase,
} from 'react-icons/fi';
import { useAuth } from '../hooks/useAuth';

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: FiHome },
  {
    label: 'Campaigns',
    icon: FiMail,
    children: [
      { path: '/campaigns', label: 'Campaigns', icon: FiMail },
      { path: '/offerings', label: 'Offerings', icon: FiBriefcase },
    ],
  },
  {
    label: 'EmailOps',
    icon: FiSend,
    children: [
      { path: '/blacklist', label: 'Blacklist', icon: FiShield },
      { path: '/templates', label: 'Mailers', icon: FiFileText },
      { path: '/logs', label: 'Email Logs', icon: FiList },
    ],
  },
  { path: '/linkedin-extractor', label: 'Profile Extractor', icon: FiUser, separatorBefore: true },
  { path: '/icp-database', label: 'ICP Database', icon: FiDatabase },
  { path: '/settings', label: 'Settings', icon: FiSettings },
];

function NavLinkItem({ path, label, icon: Icon, collapsed, nested = false }) {
  const location = useLocation();
  const isActive = location.pathname.startsWith(path);

  return (
    <Link
      to={path}
      className={`flex items-center gap-3 rounded-lg transition-all duration-200 group ${
        nested ? 'px-3 py-2 ml-2' : 'px-3 py-2.5'
      } ${
        isActive
          ? 'bg-sidebar-active text-white shadow-lg shadow-primary-500/20'
          : 'text-gray-300 hover:bg-sidebar-hover hover:text-white hover:translate-x-0.5'
      }`}
      title={collapsed ? label : undefined}
    >
      <Icon
        size={nested ? 16 : 20}
        className="flex-shrink-0 transition-transform duration-200 group-hover:scale-110"
      />
      {!collapsed && <span className={`font-medium ${nested ? 'text-xs' : 'text-sm'}`}>{label}</span>}
    </Link>
  );
}

function NavGroup({ item, collapsed }) {
  const location = useLocation();
  const Icon = item.icon;
  const childActive = item.children.some((c) => location.pathname.startsWith(c.path));
  const [open, setOpen] = useState(childActive);

  if (collapsed) {
    return (
      <div className="space-y-1">
        {item.children.map((child) => (
          <NavLinkItem key={child.path} {...child} collapsed />
        ))}
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex w-full items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
          childActive
            ? 'text-white bg-sidebar-hover'
            : 'text-gray-300 hover:bg-sidebar-hover hover:text-white'
        }`}
      >
        <Icon size={20} className="flex-shrink-0" />
        <span className="text-sm font-medium flex-1 text-left">{item.label}</span>
        <FiChevronDown
          size={14}
          className={`transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open ? (
        <div className="mt-1 space-y-0.5">
          {item.children.map((child) => (
            <NavLinkItem key={child.path} {...child} nested />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function Sidebar({ collapsed = false, onToggle }) {
  const { user, logout } = useAuth();

  return (
    <aside
      className={`fixed left-0 top-0 h-full bg-sidebar text-white transition-all duration-300 z-40 flex flex-col ${
        collapsed ? 'w-[72px]' : 'w-64'
      }`}
    >
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

      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          if (item.children) {
            return (
              <div key={item.label}>
                {item.separatorBefore ? <div className="my-3 border-t border-white/10" /> : null}
                <NavGroup item={item} collapsed={collapsed} />
              </div>
            );
          }
          return (
            <div key={item.path}>
              {item.separatorBefore ? <div className="my-3 border-t border-white/10" /> : null}
              <NavLinkItem {...item} collapsed={collapsed} />
            </div>
          );
        })}
      </nav>

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

      <button
        onClick={onToggle}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-expanded={!collapsed}
        className="absolute -right-3 top-20 w-6 h-6 bg-white rounded-full shadow-md flex items-center justify-center text-gray-600 hover:text-primary-600 transition-colors"
      >
        {collapsed ? <FiChevronRight size={14} /> : <FiChevronLeft size={14} />}
      </button>
    </aside>
  );
}
