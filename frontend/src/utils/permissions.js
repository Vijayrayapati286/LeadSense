const ADMIN_ONLY = new Set([
  'settings:write',
  'members:read',
  'members:invite',
  'members:manage',
  'access:read',
  'access:manage',
  'orgs:read',
  'orgs:onboard',
  'integrations:read',
  'integrations:manage',
]);

export function hasPermission(user, permission) {
  if (!user || !permission) return false;
  const granted = user.permissions;
  if (Array.isArray(granted) && granted.length) {
    return granted.includes(permission);
  }
  if (permission === 'orgs:onboard' || permission === 'orgs:read') {
    return user.role === 'ADMIN' && user.org_type === 'PROVIDER';
  }
  if (ADMIN_ONLY.has(permission)) {
    return user.role === 'ADMIN';
  }
  return true;
}

export function hasAnyPermission(user, permissions = []) {
  return permissions.some((permission) => hasPermission(user, permission));
}
