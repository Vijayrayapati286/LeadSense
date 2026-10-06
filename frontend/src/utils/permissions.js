const ADMIN_ONLY = new Set([
  'settings:write',
  'members:read',
  'members:invite',
  'members:manage',
  'access:read',
  'access:manage',
  'integrations:read',
  'integrations:manage',
]);

export function isProviderOrg(user) {
  return String(user?.org_type || '').toUpperCase() === 'PROVIDER';
}

export function isProviderAdmin(user) {
  return user?.role === 'ADMIN' && isProviderOrg(user);
}

export function hasPermission(user, permission) {
  if (!user || !permission) return false;
  if (permission === 'orgs:onboard' || permission === 'orgs:read') {
    return isProviderAdmin(user);
  }
  const granted = user.permissions;
  if (Array.isArray(granted) && granted.length) {
    return granted.includes(permission);
  }
  if (ADMIN_ONLY.has(permission)) {
    return user.role === 'ADMIN';
  }
  return true;
}

export function hasAnyPermission(user, permissions = []) {
  return permissions.some((permission) => hasPermission(user, permission));
}
