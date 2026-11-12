# Product photo resolution fix

The actual sample line `x_product_image` is related to `product_tmpl_id.image_128`. The previous exporter preferred that thumbnail, then reduced product image data again to fit 110 pixels. Enlarging the embedded picture exposed the loss of detail even when a high-resolution product master was available.

Use the largest available linked-product image when the sample image matches a product derivative. Preserve a distinct sample-specific photo. Embed original PNG/JPEG bytes for both image columns and apply display scaling only, retaining existing DPI handling, cell layout, image/file safety limits and import schema. Do not change any business fields or deploy to production.

Regression coverage checks source priority, matching API/ORM binary values, custom sample images, missing images, original embedded dimensions/bytes and a full Odoo import after exporting a related thumbnail's high-resolution master.

Bound cumulative decoded image data at 16 MB while collecting rows and before building an archive. Disable broad field prefetch during image collection. The existing 4 MB per-source-image, pixel-count, final 8 MB workbook and expanded-archive limits remain in place.
