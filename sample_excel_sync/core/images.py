"""Choose a full product image without replacing a distinct sample-specific photo."""

PRODUCT_IMAGE_FIELDS = ('image_1920', 'image_1024', 'image_512', 'image_256', 'image_128')


def _binary(value):
    return value.encode('ascii') if isinstance(value, str) else value


def choose_product_image(line_image, product_images):
    available = [product_images.get(name) for name in PRODUCT_IMAGE_FIELDS if product_images.get(name)]
    # Sample lines may expose a related image_128 thumbnail. Only replace it
    # with the master when it matches an existing product image exactly.
    if line_image and not any(_binary(line_image) == _binary(value) for value in available):
        return line_image
    return next(iter(available), line_image or False)
