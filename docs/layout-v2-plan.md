# Layout v2 implementation scope

Approved visible columns: Malex Model, Photo, Product Description, Factory Model, Factory, Sample Qty, Color, Remarks, Sample Ready Date, Factory Feedback. Hidden Record Key follows the ten visible columns. Only sample_color, remarks, factory_ready_date and factory_comment are editable. Never move Color/Remarks values automatically.

Reuse sample-line product_description, then linked product mlx_description_text/description/description_sale; convert existing HTML to plain text without adding packaging/certification fields. Add no business fields. Default rows are 100 pt; expand exceptionally long wrapped descriptions to avoid truncation. Blue-grey headers, yellow only on the four editable columns, proportional centered pictures, freeze C5 and keep a full sortable table.

Version the workbook schema as /2. Continue reading /1 exports with their original columns and original readonly comparison set. Bind parser schema to trusted batch schema to prevent schema-downgrade tampering. Preserve existing identity, permissions, conflict handling and transaction guards.

Live read-only check: SMP2026-0127 exists with seven lines. The production module and snapshot model are absent. Do not deploy or write production. Generate a formal offline workbook plus a separate private trusted baseline manifest; IT may register its metadata after installing the updated add-on. A local registration helper must verify a separately supplied SHA256, database/user/request identity, original row/product/factory identities and the workbook contents. It may create only an internal export snapshot, never modify sample fields. This does not make the currently uninstalled production importer available.

Implementation: test column/parser/description changes first, update mapping/generator, test original-line identity after full-row sorting, add legacy/snapshot-schema tests, implement trusted IT registration helper with tests, read SMP2026-0127 and generate/validate/render the real-data output locally, independent code review, cloud Odoo19 tests, public code-only RC. Real business workbooks and manifests stay outside the public repository.
