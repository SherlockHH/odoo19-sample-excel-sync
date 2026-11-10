# Factory-first layout and remark photos

The user's correction adds the existing sample remark photo and specifies the first three columns. Keep the existing export/edit/preview/import behavior and four editable fields.

1. Use Factory, Malex Model No, Factory Model No, Photo, Product Description, Sample Qty, Color, Remarks, Remark Photo, Sample Ready Date, Factory Feedback. Keep the row key hidden in L; freeze the first four columns and header.
2. Export the existing `x_remark_image` separately from the product photo. Missing images stay blank. Retain original PNG/JPEG remark images for enlargement while scaling display proportionally. Neither image is an import target or row identifier. Exclude image bytes from stored baselines.
3. Use schema /3 and retain original /1 and /2 import compatibility, including trusted original /2 offline registration. Reject schema substitution against a different batch.
4. Test the exact layout, separate anchors, no-photo rows, original-field mappings, duplicate-row sorting, four-field roundtrip, unchanged source image and previous versions. Regenerate the real sample workbook and its private registration package without production writes. Run isolated Odoo CI and release the verified package.

Real sample data and offline manifests must remain outside the public repository. IT deployment and native Excel/WPS acceptance are still required.
