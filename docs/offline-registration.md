# IT: register a trusted offline export after installation

This is a one-time compatibility step for a formal export produced before the add-on was installed. It is **not** a public import endpoint, a replacement for normal exports, or permission to deploy to production. No sample fields are changed by registration.

## Required trusted inputs

Obtain the following from the original trusted exporter through an approved internal channel:

1. The original **unedited** XLSX workbook retained at export time.
2. Its private `*.batch.json` baseline manifest.
3. The expected manifest SHA256, separately confirmed with that exporter.

Never take a baseline from a factory-returned workbook, public issue, or arbitrary attachment. A hash checks integrity against the value IT already trusts; a hash supplied by an untrusted sender does not authenticate that sender. The manifest contains internal record identities and original business values; do not publish it or send it to factories.

If the original workbook is edited, keep the original copy inside the retained IT package for registration. The factory may work on another copy of the XLSX with the same batch/row identifiers.

## Administrator Odoo shell

First install the updated add-on in the intended environment and complete staging acceptance. From that environment's administrator Odoo shell, with a checkout of this repository available:

```python
import sys
sys.path.insert(0, '/path/to/odoo19-sample-excel-sync/tools')
from register_offline_batch import register_batch

result = register_batch(
    env,
    '/private/path/original.batch.json',
    '/private/path/original.xlsx',
    expected_manifest_sha256='SHA256_CONFIRMED_WITH_THE_EXPORTER',
    allow_production=False,
)
print(result)
# Commit only after reviewing the result and obtaining environment approval.
env.cr.commit()
```

The helper checks original workbook hash/content, layout, token, owner login/ID, company, request and original line/product/factory identities. Current sample read/write access for the original exporter is rechecked. It creates only the internal export snapshot with its original expiry (at most 90 days); registration is idempotent for an identical existing batch. It does not reset stale originals, extend validity, change business fields, or send factory notifications.

A database name containing `live` or `prod` additionally requires an explicit `allow_production=True` supplied by IT after approval. This name check is advisory and does not reliably classify every deployment. The manifest's database name must match exactly; do not edit it to force a production workbook into an unrelated test database.

## Import the edited copy

After successful registration, the original exporter opens the same sample request, uploads the edited workbook through **Import Sample Updates**, reviews changed fields and confirms normally. All existing ACL, readonly-field, conflict, stale-preview, task and transaction protections still apply.

Normal exports created through the installed module already have their server batch. They do not need this registration step.
