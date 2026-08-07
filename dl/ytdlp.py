_classes = None


def _load() -> list:
    try:
        from yt_dlp.extractor import gen_extractor_classes
    except ImportError:
        return []
    return [cls for cls in gen_extractor_classes() if cls.IE_NAME != "generic"]


def _extractors() -> list:
    global _classes
    if _classes is None:
        _classes = _load()
    return _classes


def extractor_for(url: str):
    """The extractor yt-dlp would use for this address, or None.

    The generic extractor is left out on purpose: it claims every URL by
    fetching the page and looking for something embedded, so keeping it would
    make every address look like yt-dlp's.
    """
    if not url:
        return None
    for cls in _extractors():
        try:
            if cls.suitable(url):
                return cls
        except (TypeError, ValueError):
            continue
    return None


def return_type(url: str) -> str | None:
    """Whether the extractor yields one item, many, or will not say."""
    found = extractor_for(url)
    return getattr(found, "_RETURN_TYPE", None) if found is not None else None


def working(url: str) -> bool:
    """False only when yt-dlp itself marks the matching extractor broken."""
    found = extractor_for(url)
    return True if found is None else getattr(found, "_WORKING", True)
