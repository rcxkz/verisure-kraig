import time
import requests

_session = None


def session(user_agent):
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = user_agent
    return _session


def get(sess, url, retries=3, **kw):
    """GET with simple backoff on 429/5xx. Raises on final failure."""
    kw.setdefault("timeout", 60)
    for attempt in range(retries):
        r = sess.get(url, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
        r.raise_for_status()
        return r
    return r
