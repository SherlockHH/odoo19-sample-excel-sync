import re
from html.parser import HTMLParser


class _PlainDescription(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if not self.skip and tag in ('p', 'div', 'br', 'li', 'tr'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
        if not self.skip and tag in ('p', 'div', 'li', 'tr'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain_description(value):
    if not value:
        return ''
    value = str(value).replace('\r\n', '\n').replace('\r', '\n').strip()
    if re.search(r'</?[a-zA-Z][\w:-]*(?:\s[^<>]*)?/?>', value):
        parser = _PlainDescription()
        parser.feed(value)
        value = ''.join(parser.parts)
    return '\n'.join(line.strip() for line in value.splitlines() if line.strip())


def choose_description(line_description, product):
    """Only existing feature-description fields; never join packing/cert models."""
    for value in (line_description, *(product.get(name) for name in
                  ('mlx_description_text', 'description', 'description_sale'))):
        text = plain_description(value)
        if text:
            return text
    return ''
