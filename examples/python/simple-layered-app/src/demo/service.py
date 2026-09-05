from .repository import list_items


def item_names() -> tuple[str, ...]:
    return tuple(item.name for item in list_items())
