/** Label for a send/campaign status. Risky replaces Invalid; bad stays Invalid. */
export function deliveryStatusDisplay(status, { errorMessage, verificationStatus } = {}) {
  const key = (status || '').toLowerCase();
  const message = (errorMessage || '').toLowerCase();
  const verification = (verificationStatus || '').toLowerCase();
  const risky =
    key === 'risky' ||
    verification === 'risky' ||
    message.includes('quality=risky') ||
    message.includes('result: catch_all') ||
    message.includes('result=catch_all');

  if (risky && (key === 'invalid_email' || key === 'risky' || verification === 'risky')) {
    return { status: 'risky', label: 'Risky' };
  }
  if (key === 'invalid_email') {
    return { status: 'invalid_email', label: 'Invalid' };
  }
  return { status, label: undefined };
}
