def load_config(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def add_tag(tags, tag):
    tags.append(tag)
    return tags


def process(items, tags=None):
    if tags is None:
        tags = []
    for item in items:
        add_tag(tags, item)
    return tags
