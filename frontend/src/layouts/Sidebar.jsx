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
  FiSliders,
  FiClock,
  FiAlertCircle,
  FiUsers,
  FiChevronsRight,
  FiKey,
} from 'react-icons/fi';
import { useAuth } from '../hooks/useAuth';
import { hasAnyPermission, hasPermission, isProviderOrg } from '../utils/permissions';

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: FiHome, permission: 'dashboard:read' },
  {
    label: 'Lead Generation',
    icon: FiMail,
    children: [
      { path: '/campaigns', label: 'Campaigns', icon: FiMail, permission: 'campaigns:read' },
      { path: '/logs', label: 'Email Logs', icon: FiList, permission: 'logs:read' },
    ],
  },
  {
    label: 'ICP Database',
    icon: FiDatabase,
    children: [
      { path: '/icp-accounts', label: 'Accounts', icon: FiBriefcase, permission: 'icp:read' },
      { path: '/icp-contacts', label: 'Contacts', icon: FiUsers, permission: 'icp:read' },
    ],
  },
  {
    label: 'Profile Extraction',
    icon: FiUser,
    children: [
      { path: '/linkedin-extractor', label: 'Extract', icon: FiUser, permission: 'linkedin:extract' },
      { path: '/linkedin-history', label: 'History', icon: FiClock, permission: 'linkedin:read' },
      { path: '/linkedin-needs-review', label: 'Needs Review', icon: FiAlertCircle, permission: 'linkedin:read' },
    ],
  },
  { path: '/offerings', label: 'Offerings', icon: FiBriefcase, permission: 'offerings:read' },
  {
    label: 'Settings',
    icon: FiSettings,
    children: [
      { path: '/settings', label: 'General', icon: FiSliders, permission: 'settings:read' },
      { path: '/blacklist', label: 'Blacklist', icon: FiShield, permission: 'blacklist:read' },
      { path: '/templates', label: 'Mailers', icon: FiFileText, permission: 'mailers:read' },
    ],
  },
  {
    label: 'Members',
    icon: FiUsers,
    children: [
      { path: '/users', label: 'Members', icon: FiUsers, permission: 'members:read' },
      { path: '/invites', label: 'Invites', icon: FiMail, permission: 'members:invite' },
      { path: '/access', label: 'Roles & access', icon: FiShield, permission: 'access:read' },
    ],
  },
];

const PROVIDER_NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: FiHome, permission: 'dashboard:read' },
  { path: '/organizations', label: 'Organizations', icon: FiBriefcase, permission: 'orgs:onboard' },
  { path: '/users', label: 'Users', icon: FiUsers, permission: 'members:read' },
  { path: '/invites', label: 'Invites', icon: FiMail, permission: 'members:invite' },
  { path: '/access', label: 'Roles', icon: FiShield, permission: 'access:read' },
];

function filterNavItems(items, user) {
  return items
    .map((item) => {
      if (item.children) {
        const children = item.children.filter((child) => hasPermission(user, child.permission));
        if (!children.length) return null;
        return { ...item, children };
      }
      if (item.permission && !hasPermission(user, item.permission)) return null;
      return item;
    })
    .filter(Boolean);
}

function getNavItems(user) {
  if (isProviderOrg(user)) {
    return filterNavItems(PROVIDER_NAV_ITEMS, user);
  }
  const items = NAV_ITEMS.map((item) => {
    if (item.path === '/dashboard' && hasPermission(user, 'members:read')) {
      return { ...item, label: 'Admin Dashboard' };
    }
    return item;
  });
  return filterNavItems(items, user);
}

function initials(name) {
  return (name || 'U')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();
}

function NavLinkItem({ path, label, icon: Icon, collapsed, nested = false }) {
  const location = useLocation();
  const isActive = location.pathname === path || location.pathname.startsWith(`${path}/`);

  return (
    <Link
      to={path}
      className={`group flex items-center gap-3 rounded-lg transition-colors duration-200 ${
        nested ? 'px-3 py-2 text-[13px]' : 'px-3 py-2.5 text-sm'
      } ${
        isActive
          ? 'bg-primary-500 text-white font-medium shadow-md shadow-primary-500/25'
          : 'text-slate-400 hover:bg-white/[0.06] hover:text-white'
      }`}
      title={collapsed ? label : undefined}
    >
      <Icon size={nested ? 16 : 18} className="shrink-0 opacity-90" />
      {!collapsed && <span className="truncate">{label}</span>}
    </Link>
  );
}

function NavGroup({ item, collapsed }) {
  const location = useLocation();
  const Icon = item.icon;
  const childActive = item.children.some(
    (c) => location.pathname === c.path || location.pathname.startsWith(`${c.path}/`),
  );
  const [open, setOpen] = useState(childActive);

  if (collapsed) {
    return (
      <div className="space-y-0.5">
        {item.children.map((child) => (
          <NavLinkItem key={child.path} {...child} collapsed />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors duration-200 ${
          childActive
            ? 'text-white'
            : 'text-slate-400 hover:bg-white/[0.06] hover:text-white'
        }`}
      >
        <Icon size={18} className="shrink-0 opacity-90" />
        <span className="flex-1 truncate text-left font-medium">{item.label}</span>
        <FiChevronDown
          size={15}
          className={`shrink-0 text-slate-500 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open ? (
        <div className="space-y-0.5 pl-2">
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
  const profilePath = isProviderOrg(user) ? '/dashboard' : '/settings';

  return (
    <aside
      className={`fixed left-0 top-0 z-40 flex h-full flex-col border-r border-white/[0.06] bg-[#0b1220] text-white transition-all duration-300 ${
        collapsed ? 'w-[72px]' : 'w-64'
      }`}
    >
      {/* Brand */}
      <div className="flex h-[4.25rem] items-center gap-3 border-b border-white/[0.08] px-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-500 shadow-lg shadow-primary-500/30">
          <FiSend size={18} className="text-white" />
        </div>
        {!collapsed && (
          <div className="min-w-0 overflow-hidden">
            <h1 className="truncate text-[15px] font-bold leading-tight text-white">LeadSense</h1>
            <p className="truncate text-[11px] text-slate-500">Campaign Manager</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {getNavItems(user).map((item) => {
          if (item.children) {
            return <NavGroup key={item.label} item={item} collapsed={collapsed} />;
          }
          return <NavLinkItem key={item.path} {...item} collapsed={collapsed} />;
        })}
      </nav>

      {/* User + logout */}
      <div className="border-t border-white/[0.08] p-3">
        {!collapsed && user ? (
          <Link
            to={profilePath}
            className="mb-2 flex items-center gap-3 rounded-xl bg-white/[0.05] p-3 transition-colors hover:bg-white/[0.08]"
          >
            <div className="relative shrink-0">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-700 text-xs font-bold text-white">
                {initials(user.name)}
              </span>
              <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-[#0b1220] bg-emerald-400" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-white">{user.name}</p>
              <p className="truncate text-[11px] text-slate-500">{user.email}</p>
              <p className="truncate text-[11px] text-slate-600">
                {user.org_name || user.department || (user.role || '').replaceAll('_', ' ') || 'Member'}
              </p>
            </div>
            <FiChevronsRight size={16} className="shrink-0 text-slate-600" />
          </Link>
        ) : collapsed && user ? (
          <Link
            to={profilePath}
            title={user.name}
            className="mb-2 flex justify-center"
          >
            <span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-slate-700 text-xs font-bold">
              {initials(user.name)}
              <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-[#0b1220] bg-emerald-400" />
            </span>
          </Link>
        ) : null}

        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-400 transition-colors hover:bg-red-500/10 hover:text-red-400"
          title={collapsed ? 'Logout' : undefined}
        >
          <FiLogOut size={18} className="shrink-0" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        type="button"
        onClick={onToggle}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-expanded={!collapsed}
        className="absolute -right-3 top-[4.5rem] flex h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-md transition-colors hover:text-primary-600"
      >
        {collapsed ? <FiChevronRight size={14} /> : <FiChevronLeft size={14} />}
      </button>
    </aside>
  );
}
