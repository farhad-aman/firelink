import urllib.request


def open_url(request, timeout: float, proxy: str = ""):
    """Fetch a request, through the proxy when one applies.

    Kept apart from both callers so the direct path stays urlopen: an opener
    built for every request would route around whatever the environment
    already set up for the ones that need no proxy.
    """
    if not proxy:
        return urllib.request.urlopen(request, timeout=timeout)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    )
    return opener.open(request, timeout=timeout)
