from .service import item_names


def response() -> dict[str, tuple[str, ...]]:
    return {"items": item_names()}
