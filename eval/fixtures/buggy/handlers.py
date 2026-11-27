def load_config(path):
    try:
        with open(path) as f:
            return f.read()
    except:
        pass
    return None


def add_tag(tags, tag):
    tags.append(tag)
    return tags


DEFAULT_TAGS = add_tag([], "new")


def process(items, tags=DEFAULT_TAGS):
    for item in items:
        add_tag(tags, item)
    return tags
