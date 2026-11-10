# Sample Excel Export & Update implementation plan

> For agentic workers: implement sequentially with test-first core development and independent plan/code review.

**Goal:** Independent Odoo 19 add-on for scoped XLSX export, four-field preview and safe update of existing sample lines.

**Architecture:** Pure Python XLSX and comparison helpers; Odoo service using current-user record access; private immutable server snapshots; two transient wizards. Existing sample records remain authoritative. No customer/specification/certification columns, approval workflow or production deployment.

**Tech Stack:** Odoo 19, Python, XlsxWriter, openpyxl, Pillow, unittest; GitHub Actions; disposable Odoo/PostgreSQL integration fixture.

## Approved scope

One export button (all lines or one current-request factory), one import button. Visible columns: factory, two model numbers, picture, quantity, color/finish, other requirements, ready date, factory feedback, and read-only existing plug/logo context. System context is kept separate from editable remarks to avoid duplicate or destructive round trips. One sample line per table row. Hidden row tokens travel within the sortable Excel table. Four editable fields reuse sample_color, remarks, factory_ready_date, factory_comment. No new business fields. Request number only, no customer data. Lightweight snapshots have no management page. Clears and true conflicts require a preview choice. No unchanged-row overwrite, insert/delete, status updates or bulk email. Date synchronization targets only existing exact-linked tasks, never scans task description text.

## Tasks

- [ ] 1. Write failing pure-core tests for field-level three-way comparison, explicit clears, duplicate/foreign row identity, literal formula-like text, strict date handling, immutable columns and ZIP/XML safety limits. Run unittest and record the missing implementation failure.
- [ ] 2. Implement core/constants.py, comparison.py and workbook.py; verify tests and real XLSX round trips including image anchors and table metadata. No real business fixtures.
- [ ] 3. Add immutable metadata model, request actions, export and import wizards, access CSV and inherited form buttons. Derive allowed records on server, never trust hidden fields or preview display fields. Snapshot sudo is restricted to this add-on's internal metadata, never business records. Private methods are not RPC entry points.
- [ ] 4. Confirmation uses a trusted server preview, current-user ACLs/company/field rights, locks request/lines/tasks with ORM and rechecks values, identity, state and task association before atomic writes. Record only successful changes using existing chatter. Synchronize only changed corresponding task fields under existing recursion guards; no full project sync action.
- [ ] 5. Add framework integration tests and a clearly marked CI-only stand-in sample module. Test actual Odoo 19 permissions, preview tampering, snapshot immutability, duplicate submissions, stale preview, clear, cancelled records, task matching and rollback. The fixture is not the company's proprietary module and must never be deployed.
- [ ] 6. Add README (Chinese usage/deployment), license, local test launcher, clean packaging and CI/security checks. Document real-module staging, Excel and WPS manual acceptance as outstanding until actually performed. Never claim zero vulnerabilities.
- [ ] 7. Review code independently, fix findings, run local tests/scans/package checks. Create a clean public GitHub repository with no credentials, production configuration, customer data or old project history. Push a tested candidate and follow Actions to completion; use an RC tag until actual custom-module staging acceptance.

## Validation commands

## Review clarifications

Snapshots are bound to exporter, company, request and line set; import must be done by the original exporter. Export snapshots remain reusable for 90 days; trusted previews expire after 24 hours and are atomically consumed under a row lock. Private autovacuum deletes expired metadata. Neither original values nor decisions supplied through wizard RPC are trusted as baselines. Unchanged Excel -> skip; Excel-only edit -> update; server-only edit -> preserve; identical concurrent edits -> skip; divergent same-field edit -> explicit conflict. Empty cell -> ignore unless explicitly cleared. Re-preview is required when relevant values, states, associations or identity change after preview.

Existing Python hooks cannot be retrieved via the current read-only API. Known local recursion guards are applied narrowly, but no claim is made that they suppress every deployed automation. Live writes remain prohibited. Real-module staging acceptance is mandatory, including mail/activity/task side effects. Normal writable line states are accepted except cancelled; cancelled requests are blocked. Exact task links supported: stored sample_request_line_id or x_sample_line_id; at most one task per line; mirror only sample_ready_date/x_sample_ready_date when the completion date actually changes. No task-state synchronization. Lock before rechecking and updating; duplicate task links are errors, not arbitrary selection.

Use this repository's .venv. `python -m unittest discover -s tests -v`, `python -m ruff check .`, `python -m bandit -r sample_excel_sync -ll`, `python -m pip_audit -r requirements.txt`. CI additionally installs the add-on in official Odoo 19 with PostgreSQL and synthetic sample fixtures and runs `/sample_excel_sync` tests. Package includes only the add-on folder. No live mutations or module upload.

## Environment evidence

Read-only field metadata was checked against Odoo 19: the four target fields are stored and writable. Line supplier_id/product_tmpl_id/quantity exist. Existing x_old_malex_model and x_factory_model_no are related to product data. Current task link is x_sample_line_id; newer sample_request_line_id is absent. Production form name is mlx.sample.request.form. Local older builder code is not assumed to describe deployed Python hooks.
