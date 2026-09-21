"""Small JSON transport with bounded reads and sanitized errors."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class APIError(RuntimeError):
    pass


def post_json(url, key, payload, timeout=30):
    request = Request(url, data=json.dumps(payload).encode(), method="POST",
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise APIError("API response exceeds size limit")
        return json.loads(body)
    except HTTPError as exc:
        raise APIError(f"API HTTP {exc.code}; check credentials, quota and model settings") from None
    except (URLError, TimeoutError):
        raise APIError("API connection failed or timed out") from None
    except (ValueError, UnicodeError):
        raise APIError("API returned invalid JSON") from None
