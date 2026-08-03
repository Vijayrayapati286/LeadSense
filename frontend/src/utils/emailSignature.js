import { escapeHtml } from './helpers';

// Colors picked to match the reference signature: a corporate blue for the
// name/hyperlink and the brand red-orange for the company name.
const NAME_COLOR = '#1155cc';
const BRAND_COLOR = '#c0311a';
const SIGNATURE_STYLE = 'font-family: Calibri, Arial, sans-serif; font-size: 12px;';

/** The mandatory Feuji footer, pre-populated into every new Manual Compose
 * email so senders never have to paste it in by hand. The name line is
 * fixed placeholder text ("IST Name") edited in by hand per sender, not
 * personalized automatically — editable afterward like any other rich-text
 * content; this only supplies the starting body. */
export function buildDefaultSignature() {
  const name = escapeHtml('IST Name');

  // Color has to live on a nested <span style="color:..."> rather than
  // directly on <strong>/<a> — TipTap's Color extension only recognizes
  // `color` via its own textStyle-mark span, so a style attribute placed
  // straight on a bold/link tag gets silently dropped the moment the editor
  // parses this HTML into its document model.
  //
  // Two empty paragraphs up front give the message room before the
  // signature starts, instead of the signature sitting flush against the
  // top of an otherwise-empty editor — see RichTextEditor's content-sync
  // effect, which also parks the cursor on the first of these so typing
  // starts there immediately.
  return (
    '<p></p><p></p>' +
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
