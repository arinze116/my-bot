from __future__ import annotations

import httpx

from url_verifier import URLVerifier


def test_url_verifier_falls_back_from_head_to_get() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        status = 405 if request.method == "HEAD" else 200
        return httpx.Response(status, request=request)

    verifier = URLVerifier(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert verifier.is_resolvable("https://example.com/hack") is True
    assert methods == ["HEAD", "GET"]


def test_url_verifier_rejects_dead_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    verifier = URLVerifier(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert verifier.is_resolvable("https://example.com/missing") is False
