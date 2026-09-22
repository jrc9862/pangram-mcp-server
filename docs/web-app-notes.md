# Pangram web app: measured API surface

The only reference `scraping/client.py` has. Captured 2026-09-22 from a live,
logged-in Free account (dashboard network capture plus the app's JS bundles).
Re-measure when a call starts failing; do not guess.

## Origin and auth

- Front end: `https://www.pangram.com` (Next.js). API: `https://web.pangram.com/api/`.
- Session is a cookie on `pangram.com`; requests carry it with
  `credentials: 'include'` from the `www.pangram.com` origin. No
  `Authorization` header.
- State-changing calls send `X-CSRFToken`, taken from
  `GET /api/accounts/get-csrf/` -> `{"csrfToken": "..."}`.
- `GET /api/session-status/` is the session check:
  `isAuthenticated`, `email`, `creditsRemaining`, `creditsTotal`, `plan`,
  `haveAccessToPaidFeatures`, `lastFreeCreditUpdated`.
- Login: email/password posts to `/api/login/`; Google and SSO also offered.
  Login routes are localized (`/fr/login`), so route checks strip the prefix.

## Text scan (measured)

```
POST /api/classify-text-sliding-window/
  {"text", "source": "product", "logging": true,
   "distinctId": <email>, "include_plagiarism": false}
-> 202 {"status": "background_processing", "task_id", "credits_required"}

POST /api/classify-text-sliding-window/status/   {"task_ids": [task_id]}
-> 200 {"tasks": [{"task_id", "status": "background_processing"}]}   (repeat)
-> 200 {"tasks": [{"task_id", "status": "success", "result": {...}}]}
```

The dashboard polls about every 2 s; a 74-word scan took ~7 polls.
`result` keys: `text` (server-normalized; segment offsets index into this, not
the submitted text), `textquery_uuid`, `credits_remaining`, `ai_likelihood`,
`category_label`, and `response.overall`:
`prediction_short` (AI/Human/Mixed), `headline`, `prediction`, `fraction_ai`,
`fraction_ai_assisted`, `fraction_human`, `fraction_mixed`,
`avg_ai_likelihood`, `word_count`, `version` ("4.0"), and `windows[]` with
`start_index`, `end_index`, `label`, `confidence`, `ai_likelihood`,
`word_count`, `is_humanized`.

Cost: 1 credit per 100 words, 50-word minimum. Free plan: 20 credits and
"3 scans/day". Plagiarism needs a paid plan.

## History (measured)

- `GET /api/history-list/?search=&order=DESC&limit=10&offset=0&prediction=Human,AI,Mixed`
  -> `{count, next, previous, results[]}`; each result has `uuid`,
  `timestamp`, `file_name`, `category_label`, `prediction_prob`,
  `input_type`, `source_url`, `prompt`.
- `GET /api/history/<uuid>/` -> the full scan, same `response.overall` shape.
- Page for a scan: `https://www.pangram.com/history/<uuid>` (renders the result).

## URL scan (measured)

`POST /api/url-scan/extract/ {"url"}` -> `{text, url, truncated, word_count,
credits_cost}`. Costs nothing; the credits are spent on the classify call that
follows. Google Docs links are refused client-side by the app.

## File upload (from the bundle, not yet measured)

```
POST /api/batch-upload/ {}                      -> {id, ...}
POST /api/upload/batch/<id>/  multipart file    -> {batch_file_upload_id, ...}
GET  /api/batch-upload/<id>/status/             -> poll; shape unverified
```

`_finished_file()` reads the status defensively. The first real `.docx`/`.pdf`
scan should be captured and this section corrected.

Other endpoints seen in the bundle, unused: `/api/estimate-credits-cost/`
(multipart, for files), `/api/csv-bulk-scan/`, `/api/detection-models/`,
`/api/image-detection/*`, `/api/anonymous-scan/*`.
