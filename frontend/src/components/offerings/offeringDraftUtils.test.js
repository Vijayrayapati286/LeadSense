import assert from 'node:assert/strict';
import test from 'node:test';

import {
  acceptAiSuggestion,
  applyAllAiSuggestions,
  normalizeList,
  reconcileAiDraft,
  validateOffering,
} from './offeringDraftUtils.js';

const bankingDraft = {
  suggested_name: 'Commercial Business Growth & Lending Solutions',
  product_type: 'Financial Services',
  short_description: 'Flexible commercial lending for business growth.',
  industries: ['Banking', ' Financial Services ', 'banking'],
  job_titles: ['Commercial Banker'],
  use_cases: ['Working capital financing'],
};

test('empty fields are populated directly and marked AI generated', () => {
  const result = reconcileAiDraft({ name: '', product_type: '', target_industries: [] }, bankingDraft);
  assert.equal(result.form.name, bankingDraft.suggested_name);
  assert.equal(result.form.product_type, 'Financial Services');
  assert.deepEqual(result.form.target_industries, ['Banking', 'Financial Services']);
  assert.equal(result.provenance.name, 'ai_generated');
  assert.deepEqual(result.suggestions, {});
});

test('existing values are never silently overwritten', () => {
  const form = {
    name: 'AI Sales Platform',
    product_type: 'SaaS',
    short_description: 'Current description',
    target_industries: ['Technology'],
  };
  const result = reconcileAiDraft(form, bankingDraft);
  assert.equal(result.form.name, form.name);
  assert.equal(result.form.product_type, form.product_type);
  assert.equal(result.form.short_description, form.short_description);
  assert.deepEqual(result.form.target_industries, form.target_industries);
  assert.deepEqual(result.form.target_job_titles, ['Commercial Banker']);
  assert.equal(result.suggestions.name.current, 'AI Sales Platform');
  assert.equal(result.suggestions.name.suggested, bankingDraft.suggested_name);
  assert.deepEqual(result.suggestions.target_industries.current, ['Technology']);
});

test('one suggestion can be accepted without changing other fields', () => {
  const form = { name: 'Current', product_type: 'SaaS' };
  const reviewed = reconcileAiDraft(form, bankingDraft);
  const accepted = acceptAiSuggestion(reviewed.form, reviewed.suggestions, 'name');
  assert.equal(accepted.form.name, bankingDraft.suggested_name);
  assert.equal(accepted.form.product_type, 'SaaS');
  assert.ok(accepted.suggestions.product_type);
});

test('apply all is explicit and resolves all suggestions', () => {
  const form = { name: 'Current', product_type: 'SaaS' };
  const reviewed = reconcileAiDraft(form, bankingDraft);
  const accepted = applyAllAiSuggestions(reviewed.form, reviewed.suggestions);
  assert.equal(accepted.form.name, bankingDraft.suggested_name);
  assert.equal(accepted.form.product_type, 'Financial Services');
  assert.deepEqual(accepted.suggestions, {});
});

test('lists are trimmed and deduplicated case-insensitively', () => {
  assert.deepEqual(normalizeList([' Banking ', 'banking', 'Financial Services', '']), [
    'Banking',
    'Financial Services',
  ]);
});

test('validation rejects missing required and legacy placeholder draft', () => {
  assert.ok(validateOffering({ name: '', product_type: '' }).name);
  assert.ok(validateOffering({ name: 'Name', product_type: '' }).product_type);
  assert.ok(
    validateOffering({
      name: 'AI Sales Platform',
      product_type: 'SaaS',
      short_description: 'AI-powered platform for B2B sales teams',
    }).name,
  );
});
