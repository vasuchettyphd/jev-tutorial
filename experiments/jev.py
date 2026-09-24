"""Minimal client for Jev on OpenRouter's decisions endpoint (standard library only)."""
import json, os, time, urllib.error, urllib.request

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
RETRYABLE = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524}  # 52x: Cloudflare edge errors


def ask(state, questions, tries=4):
    """Send one state plus questions to Jev and return the parsed response.

    Retries only rate limits, server errors and network failures. A 4xx such as
    a bad key or an empty balance raises immediately instead of being retried.
    A retried request may be billed twice if the first one did reach the server.
    """
    key = os.environ["OPENROUTER_API_KEY"]
    body = json.dumps({"model": MODEL, "state": state, "questions": questions}).encode()
    for i in range(tries):
        req = urllib.request.Request(URL, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE or i == tries - 1:
                raise
            wait = float(e.headers.get("Retry-After") or 2 ** i)
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
            wait = 2 ** i
        time.sleep(wait)
