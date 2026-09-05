from .model import Item


def list_items() -> tuple[Item, ...]:
    return (Item("example"),)
