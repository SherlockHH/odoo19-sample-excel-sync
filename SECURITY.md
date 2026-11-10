# Security

Please report a suspected vulnerability privately to the repository owner through a channel approved by your organization. Do not attach production credentials, customer files or sensitive workbook contents to public issues.

This add-on does not accept executable code, new product rows, arbitrary field names, macros or external workbook links. Its business writes use the current Odoo user's normal access. Internal snapshot operations are narrowly elevated and are not exposed through RPC methods.

Use an isolated Odoo staging environment with the actual existing custom modules before production deployment. CI-only synthetic fixtures do not establish production compatibility. Review dependency audit and framework integration results for the exact commit being deployed.
