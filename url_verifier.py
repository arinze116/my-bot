from __future__ import annotations

import httpx


class URLVerifier:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
        )

    def is_resolvable(self, url: str) -> bool:
        try:
            response = self.client.head(url)
            if 200 <= response.status_code < 400:
                return True
            response = self.client.get(url, headers={"Range": "bytes=0-1024"})
            return 200 <= response.status_code < 400
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
