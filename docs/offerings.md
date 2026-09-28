# Offerings table and APIs

All offering routes are mounted at **`/api/offerings`**.

- **JWT** (LeadSense UI): full product definition, matching, and campaign handoff.
- **PAT** (SmartOps): create / update / list a document offering for the PAT’s organization.

Source: `backend/app/offerings/models.py`, `backend/app/offerings/routes.py`, `backend/app/offerings/sync_service.py`.

---

## `offerings` table

ORM: `OfferingRow` · indexes: `(user_id, status)`, `(user_id, updated_at)`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | Integer PK | no | Internal auto-increment (UI + matching FKs) |
| `offering_id` | String(64) unique | yes | Public id `ls_off_…` for SmartOps |
| `organization_id` | String(64) FK → `organizations.org_id` | yes | Same value as `organizations.org_id` (e.g. `org_8ab2…`) |
| `smartops_offering_id` | String(128) | yes | SmartOps idempotency key |
| `user_id` | Integer FK → `users.id` | yes | Owner |
| `name` | String(255) | no | |
| `short_description` | String(500) | yes | |
| `description` | Text | yes | |
| `product_type` | String(100) | yes | |
| `website_url` | String(500) | yes | |
| `target_customer` | Text | yes | |
| `target_industries` | JSON | yes | List of strings |
| `target_company_size` | JSON | yes | List of strings |
| `company_size_min` | Integer | yes | |
| `company_size_max` | Integer | yes | |
| `company_size_label` | String(100) | yes | |
| `revenue_min` | Integer | yes | |
| `revenue_max` | Integer | yes | |
| `target_geographies` | JSON | yes | |
| `business_models` | JSON | yes | |
| `target_departments` | JSON | yes | |
| `target_job_titles` | JSON | yes | |
| `target_seniority` | JSON | yes | |
| `decision_maker_types` | JSON | yes | |
| `buying_roles` | JSON | yes | |
| `buyer_personas` | JSON | yes | |
| `pain_points` | JSON | yes | |
| `business_problems` | JSON | yes | |
| `current_challenges` | JSON | yes | |
| `use_cases` | JSON | yes | |
| `desired_outcomes` | JSON | yes | |
| `benefits` | JSON | yes | |
| `selling_points` | JSON | yes | |
| `must_have_rules` | JSON | yes | |
| `nice_to_have_rules` | JSON | yes | |
| `exclusion_rules` | JSON | yes | |
| `positive_keywords` | JSON | yes | |
| `negative_keywords` | JSON | yes | |
| `pricing_range` | String(100) | yes | |
| `hard_filter_rules` | JSON | yes | See defaults below |
| `embedding` | JSON | yes | Vector used for matching |
| `embedding_model` | String(100) | yes | |
| `profile_text` | Text | yes | Text used to build embedding |
| `vouchers` | JSON | yes | List of `{file_id, filename, file_size, mime_type, uploaded_at}` |
| `email_template` | JSON | yes | `{name, subject, body, source_filename, uploaded_at, source}` |
| `file_format` | String(16) | yes | Legacy v1 single-file snapshot |
| `file_name` | String(500) | yes | Legacy v1 single-file snapshot |
| `file_url` | Text | yes | Legacy v1 single-file snapshot |
| `doc_count` | Integer | no | Number of SmartOps documents (default 0) |
| `status` | String(32) | no | `active` (default), `archived`, `draft` |
| `definition_version` | Integer | no | Default `1`; increments when definition changes |
| `definition_hash` | String(64) | yes | |
| `created_at` | DateTime(tz) | no | Server default now |
| `updated_at` | DateTime(tz) | no | Server default / on update |

Default `hard_filter_rules`:

```json
{
  "require_industry_overlap": true,
  "require_geography_overlap": false,
  "require_company_size_overlap": false,
  "require_role_overlap": false,
  "min_role_token_overlap": 0.4
}
```

Migrations that built this table: `016_offerings`, `017_offering_recommendation_engine`, `021_offering_vouchers`, `022_offering_email_template`, `025_offering_draft_fields`.

---

## Related tables

### `offering_documents`

SmartOps files attached to an offering. Many documents per offering. PK is the SmartOps `doc_id` (`odoc_…`). `offering_id` is the public `ls_off_…` value.

| Column | Type | Notes |
|---|---|---|
| `doc_id` | String(128) PK | SmartOps document id |
| `offering_id` | String(64) FK → `offerings.offering_id` CASCADE | |
| `file_name` | String(500) | Original filename |
| `file_format` | String(16) | `pdf`, `docx`, `pptx`, `txt` |
| `s3_key` | Text | SmartOps storage key |
| `created_at` | DateTime(tz) | |

### `offering_matches`

One row per offering × ICP record. Unique on `(offering_id, icp_record_id)`.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `offering_id` | Integer FK → `offerings.id` CASCADE | |
| `icp_record_id` | Integer FK → `icp_records.id` CASCADE | |
| `fit_score` | Integer | Overall 0–100 |
| `industry_score` | Integer | |
| `job_title_score` | Integer | |
| `department_score` | Integer | |
| `company_size_score` | Integer | |
| `pain_use_case_score` | Integer | |
| `seniority_score` | Integer | |
| `buying_signal_score` | Integer | |
| `icp_fit_score` | Integer | Spec component 0–100 |
| `problem_fit_score` | Integer | |
| `role_fit_score` | Integer | |
| `company_fit_score` | Integer | |
| `historical_score` | Integer | Default 70 |
| `semantic_similarity` | Integer | |
| `missing_information` | JSON | |
| `explanation` | Text | |
| `match_tier` | String(32) | `strong` (≥80), `good` (≥65), `potential` (≥50), `poor` |
| `match_reasons` | JSON | |
| `ai_analysis` | JSON | |
| `status` | String(32) | `new`, `ai_matched`, `needs_review`, `approved`, `rejected` |
| `offering_definition_version` | Integer | |
| `reviewed_by` | Integer FK → `users.id` | |
| `reviewed_at` | DateTime(tz) | |
| `created_at` / `updated_at` | DateTime(tz) | |

### `offering_match_jobs`

Background matching job.

| Column | Type | Notes |
|---|---|---|
| `id` | String(36) PK | UUID |
| `offering_id` | Integer FK CASCADE | |
| `user_id` | Integer FK | |
| `status` | String(32) | `pending`, `running`, `done`, `failed` |
| `total_count` | Integer | |
| `processed_count` | Integer | |
| `strong_count` / `potential_count` / `poor_count` / `error_count` | Integer | |
| `definition_version` | Integer | |
| `error` | Text | |
| `started_at` / `completed_at` | DateTime(tz) | |
| `created_at` / `updated_at` | DateTime(tz) | |

### `offering_match_job_items`

Per-ICP work items for a job. Unique on `(job_id, icp_record_id)`.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `job_id` | String(36) FK CASCADE | |
| `icp_record_id` | Integer FK CASCADE | |
| `status` | String(32) | `QUEUED`, `PROCESSING`, `SUCCESS`, `FINAL_FAILED`, `SKIPPED` |
| `error` | Text | |
| `attempts` | Integer | Default 0 |
| `created_at` / `updated_at` | DateTime(tz) | |

### `offering_recommendation_feedback`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `recommendation_id` | Integer FK → `offering_matches.id` CASCADE | |
| `offering_id` | Integer FK CASCADE | |
| `icp_record_id` | Integer FK CASCADE | |
| `user_id` | Integer FK | |
| `action` | String(32) | `viewed`, `accepted`, `rejected`, `recommended`, `converted` |
| `score_at_action` | Integer | |
| `created_at` | DateTime(tz) | |

---

## Offering APIs

Base path: `/api/offerings`

### CRUD

#### `GET /api/offerings`

List offerings for the current user.

| Query | Type | Default | Notes |
|---|---|---|---|
| `search` | string | `""` | |
| `page` | int ≥ 1 | `1` | |
| `limit` | int 1–100 | `25` | Page size |
| `page_size` | int 1–100 | — | Overrides `limit` if set |

**Response `OfferingListResponse`**

```json
{
  "items": [ { "id": 1, "name": "Cloud migration", "status": "active", "...": "..." } ],
  "total": 1,
  "page": 1,
  "page_size": 25
}
```

Each item is `OfferingResponse` (all table fields plus optional list stats: `total_matches`, `strong_matches`, `potential_matches`, `approved_matches`). `description` is also exposed as `detailed_description`. Embeddings are not returned.

#### `POST /api/offerings` → `201`

Create an offering. Body: `OfferingCreate`.

Required: `name`. Optional: all other offering fields listed in the table, plus `vouchers`, `email_template`, `status` (default `"active"`). List fields accept an array or a newline/comma-separated string (deduped, trimmed).

**400** invalid payload · **500** DB error (often missing `vouchers` / `email_template` columns if migrations were not applied).

#### `GET /api/offerings/{offering_id}`

Get one offering owned by the current user. **404** if missing.

#### `PUT /api/offerings/{offering_id}`

Partial update. Body: `OfferingUpdate` (`name` optional). **404** / **400** / **500** as above.

#### `DELETE /api/offerings/{offering_id}`

```json
{ "ok": true, "id": 12 }
```

---

### AI helpers

#### `POST /api/offerings/generate-icp`

Generate ICP fields from a product description (no offering id required).

**Body `GenerateIcpRequest`**

```json
{
  "description": "At least 10 characters of offering text",
  "requested_fields": [],
  "current_values": {}
}
```

**Response `GeneratedIcpPayload`**: industries, company_size `{min,max,label}`, departments, job_titles, seniority, geographies, business_models, decision_maker_types, buying_roles, pain_points, business_problems, use_cases, desired_outcomes, benefits, selling_points, keywords, rules, plus optional `suggested_name`, `short_description`, `description`, `product_type`, `target_customer`, `pricing_range`, `is_mock`.

#### `POST /api/offerings/{offering_id}/generate-icp`

Same as above, but **404** if the offering is missing. Uses `body.description` or falls back to the offering’s stored description.

#### `POST /api/offerings/generate-email-templates`

Generate 2–3 outreach email variants.

**Body `GenerateOfferingEmailRequest`**

```json
{
  "name": "Required",
  "short_description": null,
  "description": null,
  "product_type": null,
  "target_industries": [],
  "target_job_titles": [],
  "target_geographies": [],
  "company_size_label": null,
  "pain_points": [],
  "use_cases": [],
  "benefits": [],
  "desired_outcomes": [],
  "decision_maker_types": [],
  "buying_roles": [],
  "tone": "formal",
  "additional_context": null,
  "count": 3
}
```

`count` is 2–3 (default 3).

**Response**

```json
{
  "versions": [
    { "angle": "...", "subject": "...", "body": "...", "closing": "", "cta": "" }
  ],
  "is_mock": false
}
```

#### `POST /api/offerings/parse-email-template`

`multipart/form-data` with field `file`. Parses an uploaded template.

**Response `OfferingEmailTemplateMeta`**

```json
{
  "name": "Introduction Outreach",
  "subject": "...",
  "body": "...",
  "source_filename": "intro.html",
  "uploaded_at": null,
  "source": "upload"
}
```

**400** if the file fails validation.

---

### Matching

#### `POST /api/offerings/{offering_id}/match`

Start an async match job against ICP records.

| Query | Type | Default |
|---|---|---|
| `force` | bool | `false` |
| `verified_only` | bool | `false` |

**Response `MatchingJobStatusResponse`**

```json
{
  "job_id": "uuid",
  "status": "pending",
  "total_count": 0,
  "processed_count": 0,
  "strong_count": 0,
  "potential_count": 0,
  "poor_count": 0,
  "error_count": 0,
  "percent": 0,
  "error": null,
  "started_at": null,
  "completed_at": null
}
```

#### `GET /api/offerings/{offering_id}/matching-status`

Latest job, or `{ "job_id": null, "status": "idle", ... }` if none.

#### `GET /api/offerings/{offering_id}/stats`

**Response `OfferingStatsResponse`**

```json
{
  "total_candidates": 0,
  "strong_matches": 0,
  "potential_matches": 0,
  "poor_matches": 0,
  "approved": 0,
  "rejected": 0,
  "pending_review": 0,
  "needs_review": 0
}
```

#### `GET /api/offerings/{offering_id}/matches`

List matches for one offering.

| Query | Alias | Notes |
|---|---|---|
| `search` | | |
| `match_tier` | | `strong` / `good` / `potential` / `poor` |
| `status` | `status_filter` | Match status |
| `industry` | | |
| `company_size` | | |
| `designation` | | |
| `seniority` | | |
| `location` | | |
| `verification_status` | | ICP verification |
| `min_score` / `max_score` | | |
| `sort_by` | default `fit_score` | |
| `sort_order` | default `desc` | |
| `page` | default `1` | |
| `limit` / `page_size` | default `25`, max `100` | |

**Response `OfferingMatchListResponse`**: `{ items, total, page, page_size }`. Each item is `OfferingMatchResponse` (scores + joined ICP fields: `name`, `company_name`, `designation`, `industry`, `company_size`, `location`, `linkedin_url`, `about`, `icp_verification_status`).

#### `GET /api/offerings/{offering_id}/matches/{match_id}`

One match. **404** if offering or match missing.

#### `POST /api/offerings/{offering_id}/matches/{match_id}/approve`

Sets status to `approved`, records reviewer. Returns `OfferingMatchResponse`.

#### `POST /api/offerings/{offering_id}/matches/{match_id}/reject`

Sets status to `rejected`. Returns `OfferingMatchResponse`.

#### `PUT /api/offerings/{offering_id}/matches/{match_id}`

**Body `MatchStatusUpdate`**

```json
{ "status": "approved", "notes": null }
```

**400** if status is invalid.

#### `GET /api/offerings/by-icp/{icp_record_id}`

Top recommended offerings for a verified ICP record (org-scoped).

| Query | Default |
|---|---|
| `min_score` | `50` (0–100) |
| `limit` | `5` (1–25) |
| `sort_by` | `fit_score` |

```json
{ "items": [ ... ], "total": 3 }
```

**404** if the ICP record is not in the caller’s org.

#### `POST /api/offerings/matches/{match_id}/feedback`

**Body**

```json
{ "action": "accepted", "notes": null }
```

Allowed `action`: `viewed`, `accepted`, `rejected`, `recommended`, `converted`.

`accepted` also sets the match to `approved`; `rejected` sets it to `rejected`.

```json
{
  "id": 1,
  "recommendation_id": 10,
  "offering_id": 2,
  "icp_record_id": 33,
  "action": "accepted",
  "score_at_action": 82,
  "created_at": "2026-09-24T10:00:00+00:00"
}
```

---

### Campaign handoff

#### `POST /api/offerings/{offering_id}/prepare-campaign-recipients`

Turn approved/selected matches into campaign recipients.

**Body**

```json
{
  "match_ids": [1, 2],
  "icp_record_ids": [],
  "campaign_id": 15,
  "group_name": null
}
```

At least one of `match_ids` or `icp_record_ids` is required (**400** otherwise).

**Response**

```json
{
  "recipient_ids": [101, 102],
  "tagged": 2,
  "skipped": [{ "name": "Acme", "reason": "No email" }]
}
```

---

## SmartOps PAT sync

Same connector PAT as leads / whoami: `Authorization: Bearer {PAT}`.

`organization_id` is **`organizations.org_id`** — the organizations table primary key (values like `org_8ab2231c1164f58bfd2d5356`). It is not a SmartOps `ten_…` id.

The PAT already belongs to one org. That org’s `org_id` is used as `offerings.organization_id`. If the body/query sends `organization_id` and it is not that same `organizations.org_id`, the API returns **404**.

Do **not** create a second `offerings` table. SmartOps writes into this same table. Documents go in `offering_documents`.

### `POST /api/offerings`

Create or return the existing row for `(organization_id, smartops_offering_id)`. Documents in `docs[]` are upserted by `doc_id`.

```json
{
  "organization_id": "org_8ab2231c1164f58bfd2d5356",
  "smartops_offering_id": "off_01KYVG27FVHC98JYHWN2FRCBPH",
  "name": "Enterprise Pitch Pack",
  "description": "Q4 enterprise solution overview with pricing",
  "doc_count": 2,
  "docs": [
    {
      "doc_id": "odoc_01M3CP0TVBW0X7NE8THKGNHMCV",
      "offering_id": "off_01KYVG27FVHC98JYHWN2FRCBPH",
      "file_name": "pitch_deck.pdf",
      "file_format": "pdf",
      "s3_key": "offerings/ten_xxx/pitch_deck.pdf",
      "created_at": "2026-09-25T15:30:00Z"
    }
  ],
  "created_at": "2026-09-25T10:00:00Z"
}
```

**201** first sync, **200** if that SmartOps id already exists for the org.

```json
{
  "offering_id": "ls_off_abc123",
  "organization_id": "org_8ab2231c1164f58bfd2d5356",
  "name": "Enterprise Pitch Pack",
  "status": "active",
  "doc_count": 2,
  "created_at": "2026-09-25T10:00:00+00:00"
}
```

SmartOps should store `offering_id` as `leadsense_offering_id`.

### `PUT /api/offerings/{offering_id}`

Re-sync an already-synced offering (`ls_off_…`) when metadata or new docs change. Same body as create. Incoming `docs[]` are upserted (existing `doc_id` updated, new ids inserted). **200**.

### `GET /api/offerings?organization_id={org_id}`

```json
{ "items": [ { "offering_id": "ls_off_abc123", "name": "Enterprise Pitch Pack", "doc_count": 2, "status": "active", "created_at": "..." } ] }
```

| HTTP | SmartOps should |
|---|---|
| 201 / 200 | `sync_status = synced`, store `offering_id` |
| 401 | Invalid token |
| 404 | Org id does not match the PAT |
| 400 | Missing `name`, `smartops_offering_id`, `doc_id`, `file_name`, or bad `file_format` |
| 5xx | Retry up to 3 times |

v1 single-file bodies (`file_name` / `file_format` at the top level, no `docs`) are still accepted and stored as one document.

---

## Related file API (vouchers)

Not under `/offerings`, but used by offering collateral:

`POST /api/files/upload?purpose=offering_voucher` — `multipart/form-data` field `file`. Optional `batch_id`. Returns a stored file used in `offerings.vouchers[].file_id`.

`GET /api/files/{fileId}/content` — download the voucher blob.

---

## Auth and errors

| Status | When |
|---|---|
| 401 | Missing / invalid JWT or PAT |
| 400 | Validation, invalid feedback action, empty recipient selection |
| 404 | Offering, match, ICP, or recommendation not found (or not in the user’s org) |
| 500 | Database error (including unapplied offering columns) |

Scoring weights used by the matcher (`SCORE_WEIGHTS_V2`): ICP fit 25%, problem fit 20%, role fit 15%, industry fit 15%, company fit 10%, buying signal 10%, historical 5%.
