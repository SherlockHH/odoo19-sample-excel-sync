# Sample Excel Export & Update — Odoo 19

English | [简体中文](README.zh-CN.md)

An independent Odoo 19 add-on for exporting sample requests to Excel and previewing updates returned by factories. Odoo remains the source of truth.

**Release status: candidate.** Automated integration tests use a synthetic Sample Request contract. They do not establish compatibility with your company's existing custom modules or verify Excel/WPS behavior. Install in isolated staging first.

## Workflow

1. Open a Sample Request and click **Export Sample Excel**. Choose **All Sample Lines** or **Selected Factory** within that request.
2. Send the workbook to the factory. Edit only the blue columns: **Color & Finish**, **Other Sample Requirements**, **Sample Ready Date**, and **Factory Feedback**.
3. The **original exporter** opens the same request and clicks **Import Sample Updates** to upload the returned workbook.
4. Click **Preview Changes**. Only changed fields appear. Ordinary updates default to Excel; clears default to ignore. Resolve genuine conflicts by choosing Excel or the current Odoo value.
5. Click **Confirm Update**. Successful field changes are recorded in the request's existing chatter. The next export includes the saved values.

Sample Ready Date accepts a real Excel date or `YYYY-MM-DD` text. Put TBC, provisional timing, and explanations in Factory Feedback. Quantities and identification columns are read-only references. Removing an Excel row does not delete its Odoo record, and new sample rows cannot be imported.

## Workbook contents

One sample line per table row, with a product thumbnail:

| Column | Import behavior |
|---|---|
| Factory | Reference only |
| Malex Model | Reference only |
| Factory Model | Reference only |
| Photo | Reference only |
| Sample Qty | Reference only |
| Color & Finish | Updates `sample_color` |
| Other Sample Requirements | Updates `remarks` |
| Sample Ready Date | Updates `factory_ready_date` |
| Factory Feedback | Updates `factory_comment` |
| Plug / Logo | Reference only |
| Line Status | Reference only |

No customer information, specifications, or certifications are exported. The heading contains only the request reference. Existing plug/logo values stay separate from editable remarks to prevent duplicated text on repeated round trips.

Series-level requirements must already be assigned to the relevant Odoo sample lines. The add-on does not infer them from old spreadsheet positions. Existing remark images (`x_remark_image`) are not exported in V1; record important requirements as text before use. A product thumbnail does not replace sample instructions.

## Sorting and limits

- Sort/filter the **entire Excel table**, which includes its hidden Record Key column. Do not sort a subset of columns, rename headers, or remove the hidden metadata sheet.
- Images are configured to move and resize with cells. Actual sorting behavior still needs manual acceptance in Excel and WPS. Import never uses an image to identify a record.
- Missing model numbers or quantities do not prevent updates when row identity is valid. Edited identification columns require a fresh export.
- Maximum 2,000 rows, 8 MB uploaded file, 48 MB expanded archive, and 8,000 characters per text cell.
- Macros, embedded active objects, external links, formulas, and error cells are rejected. Formula-like source remarks such as `=...` are exported as literal text.
- Export snapshots expire after 90 days; previews expire after 24 hours. Expired internal metadata is removed by Odoo autovacuum. There is no batch management screen.
- Factories do not need Odoo accounts. Returned workbooks are imported by the original exporter. Handle workbook business data under your company's sharing rules.

## Installation for IT

This module contains Python code and must be deployed to the Odoo service's addons path. Downloading the repository does not install it. A browser ZIP-import feature may not support Python add-ons.

1. Confirm **Odoo 19** with the company's existing `sample_management_mlx`, `project`, and `mail` modules installed.
2. Back up the staging database and filestore. Disable real outgoing email, SMS, webhooks, and other external delivery in staging.
3. Install the libraries in root `requirements.txt` into the **Python environment used by the Odoo service**. Validate compatibility before changing the service's existing dependencies.
4. Copy only **`sample_excel_sync/`** into a custom addons path, or extract the dedicated module ZIP from a release.
5. Restart Odoo, update the Apps list, and install **Sample Excel Export & Update**.
6. Complete staging acceptance, then back up production and deploy the same tested commit. For later code updates, upgrade with `-u sample_excel_sync`.

**Never deploy `ci/fixtures/sample_management_mlx`. It is a synthetic test substitute, not the company's business module.**

```text
sample_excel_sync/   Installable add-on, including Odoo integration tests
tests/              Core tests that do not require Odoo
ci/fixtures/        Synthetic contract used only by CI
ci/Dockerfile       Official Odoo 19 test image with required libraries
tools/package.py    Builds a ZIP containing only the installable add-on and docs
docs/               Design, testing, and acceptance information
```

## Compatibility contract

The add-on reuses `mlx.sample.request` and `mlx.sample.request.line`. It adds no business fields and creates/deletes no sample lines.

The request model must provide `company_id`, `state`, `name`, and `line_ids`. Lines must provide `request_id`, `supplier_id`, `product_tmpl_id`, `quantity`, `state`, and the four writable fields listed above.

The base request form is inherited by its verified unique name, `mlx.sample.request.form`. If that name has changed or several primary forms share it, IT must adjust the inheritance target in staging.

Cancelled sample lines are exported and labelled but cannot be updated. Cancelled or resolved requests must be reopened through the existing business workflow before import.

### Existing task synchronization

Exact links through `project.task.sample_request_line_id` or legacy `x_sample_line_id` are supported. Duplicate, conflicting, or cross-company links are rejected. Task descriptions are never used for fuzzy matching.

Only a changed Sample Ready Date is mirrored to the existing linked task's `sample_ready_date` / `x_sample_ready_date`. The add-on does not create tasks, intentionally change status, or schedule activities.

During its private import write section, an internal ContextVar narrowly skips these two known legacy server actions that perform broad project synchronization/status follow-up:

- `sample_request_project_link.action_auto_sample_line_lifecycle`
- `sample_request_project_link.action_auto_sample_task_stage_followup`

Existing recursion guards are also supplied. The scope is limited to this add-on's import call stack: no automation configuration is changed, and other actions are not suppressed. If those XML IDs are absent, normal execution continues. Unknown overrides or automations may still exist; **IT must verify side effects with the actual custom modules**. Unexpected protected changes roll the import back.

## Access, conflicts, and integrity

The two transient wizards are available to internal users. Business field reads/writes use the current user's ORM access, record rules, field permissions, and selected companies. A narrowly elevated **count of exact-linked tasks** detects links hidden by record rules; the operation then refuses without revealing task IDs or contents.

Hidden cells contain opaque identifiers. Actual line IDs, scope, original values, and preview plans are stored in private server-side snapshots. Ordinary users cannot create, read, or edit them. Elevated operations are limited to internal metadata storage and the association-count check. Snapshots are bound to exporter, request, and company.

Confirmation locks the preview, request, relevant sample lines, and existing tasks. It rechecks file hash, permissions, current values, product/factory/request identity, states, and task associations. Writes come from the trusted server plan, not mutable preview display fields. A preview is consumed once; re-importing the same file naturally produces no changes after a successful save.

After writes and chatter logging, the add-on checks the request's line identities, quantities, states, four editable fields, and exact-linked tasks' dates, states, assignees, and projects. Changes outside the permitted update set cause rollback.

**Concurrency boundary:** legacy `x_sample_line_id` is an integer link. Other modules may create or rebind tasks in separate transactions without locking sample rows. This add-on does not add global hooks to every task mutation and does not claim fully serialized association changes. IT must test this scenario and avoid simultaneous task relinking during imports.

A failed confirmation rolls back its transaction. Reverting code does **not** undo previously imported business data; use the change notes for manual correction or IT's tested database/filestore recovery procedure.

## Development and checks

On Windows, create `.venv` at the repository root and install `requirements-dev.txt`. The included batch launcher runs core tests; it does not start an Odoo server.

```shell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m bandit -r sample_excel_sync -ll
.venv\Scripts\python -m pip_audit -r requirements.txt
.venv\Scripts\python tools/package.py
```

GitHub Actions runs these checks and installs/tests the add-on in official Odoo 19 with PostgreSQL and synthetic sample fixtures. It uses disposable data, never connects to production, and requires no production credentials.

Passing scans does not establish absence of vulnerabilities. Tool rules, advisory databases, and test coverage have limits. See the [staging acceptance checklist](docs/acceptance.md).

## Public repository policy

Include only original add-on code, documentation, and synthetic test data. Do not commit real sample workbooks, customer information, credentials, API keys, production connection settings, database/filestore backups, proprietary existing-module source, or local environments. The CI database password is only for a disposable PostgreSQL service.

License: **LGPL-3.0-or-later**. Third-party libraries and existing Odoo/business modules retain their respective licenses.
