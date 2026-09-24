def page(items, number, size):
    """Return the 1-based page ``number`` of ``items``."""
    start = number * size
    return items[start : start + size]
