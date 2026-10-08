import { escapeHtml } from './helpers';

// Colors picked to match the reference signature: a corporate blue for the
// name/hyperlink and the brand red-orange for the company name.
const NAME_COLOR = '#1155cc';
const BRAND_COLOR = '#c0311a';
const SIGNATURE_STYLE = 'font-family: Calibri, Arial, sans-serif; font-size: 12px;';

const SIGNATURE_MARKER = 'Feuji Software Solutions';

/** The mandatory Feuji footer. The name line is fixed placeholder text
 * ("IST Name") edited in by hand per sender, not personalized automatically
 * — editable afterward like any other rich-text content. */
function signatureHtml() {
  const name = escapeHtml('IST Name');

  // Color has to live on a nested <span style="color:..."> rather than
  // directly on <strong>/<a> — TipTap's Color extension only recognizes
  // `color` via its own textStyle-mark span, so a style attribute placed
  // straight on a bold/link tag gets silently dropped the moment the editor
  // parses this HTML into its document model.
  return (
    `<div style="${SIGNATURE_STYLE}">` +
    '<p>Thanks &amp; Best,<br>' +
    `<strong><span style="color:${NAME_COLOR};">${name}</span></strong></p>` +
    '<p>' +
    `<strong><span style="color:${BRAND_COLOR};">Feuji Software Solutions</span></strong> | ` +
    `<a href="https://www.feuji.com" target="_blank" rel="noopener noreferrer"><span style="color:${NAME_COLOR};">www.feuji.com</span></a><br>` +
    '6363 N State Highway 161, Ste 250, Irving, TX 75038<br>' +
    '<strong>USA | Costa Rica | India</strong><br>' +
    '<strong>Core Values:</strong> Wow the customer | Simpler is better | Walk the talk | Spread the cheer | Pay it forward' +
    '</p>' +
    '<p><em>Disclaimer: If you\'re not interested in this conversation, please let me know and I\'ll remove you from my contact list.</em></p>' +
    '</div>'
  );
}

/** Starting body for a blank Manual Compose email. Two empty paragraphs
 * up front give the message room before the signature, instead of the
 * signature sitting flush against the top of an otherwise-empty editor —
 * see RichTextEditor's content-sync effect, which also parks the cursor
 * on the first of these so typing starts there immediately. */
export function buildDefaultSignature() {
  return `<p></p><p></p>${signatureHtml()}`;
}

function isBlankManualBody(body) {
  if (!body) return true;
  const stripped = body.replace(/<[^>]*>/g, '').replace(/&nbsp;/gi, ' ').trim();
  if (stripped.length > 0) return false;
  return !/<(img|table)\b/i.test(body);
}

/** The Offering Email "Introduction Outreach" starter. It belongs on that
 * tab, not in Manual — including when the merge tags were saved with extra
 * braces (`{{{{Name}}}}`). */
const OUTREACH_STARTER = /(?:<p>\s*)?Hello\s+\{\{+\s*Name\s*\}+[\s\S]*?brief chat\??\s*(?:<\/p>)?/gi;

function withoutOutreachStarter(body) {
  if (!body || !/Hello\s+\{\{+\s*Name/i.test(body)) return body || '';
  return body.replace(OUTREACH_STARTER, '').replace(/(?:<p>\s*<\/p>\s*)+$/i, '');
}

function isOnlySignoff(body) {
  const text = (body || '')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/g, '&')
    .trim();
  return text === 'Thanks & Best,' || text === 'Thanks & Best';
}

/** Put the Feuji footer back on a Manual body that lost it, and drop the
 * Introduction Outreach greeting if it was carried into Manual.
 * Bodies that already include the footer keep the sender's edited name. */
export function withDefaultSignature(body) {
  const cleaned = withoutOutreachStarter(body);
  if (cleaned && cleaned.includes(SIGNATURE_MARKER)) return cleaned;
  if (isBlankManualBody(cleaned) || isOnlySignoff(cleaned)) return buildDefaultSignature();
  return `${cleaned}${signatureHtml()}`;
}
