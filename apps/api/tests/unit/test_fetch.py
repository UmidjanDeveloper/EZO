import httpx
import pytest

from ezo_api.knowledge.fetch import FetchError, SafeFetcher


def _resolver(mapping: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    async def resolve(host: str, port: int) -> list[str]:
        return mapping.get(host, ["93.184.216.34"])

    return resolve


def _fetcher(handler, mapping: dict[str, list[str]] | None = None) -> SafeFetcher:  # type: ignore[no-untyped-def]
    return SafeFetcher(transport=httpx.MockTransport(handler), resolver=_resolver(mapping or {}))


def _page(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(
        200, headers={"content-type": "text/html; charset=utf-8"}, text="<p>ok</p>"
    )


async def test_public_page_is_fetched() -> None:
    page = await _fetcher(_page).fetch("https://example.com/news")
    assert page.content_type == "text/html"
    assert page.data == b"<p>ok</p>"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "http://user:pass@example.com/",
        "http://127.0.0.1/admin",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://100.64.1.1/",
    ],
)
async def test_unsafe_urls_are_blocked(url: str) -> None:
    with pytest.raises(FetchError):
        await _fetcher(_page).fetch(url, respect_robots=False)


async def test_hostname_resolving_to_private_ip_is_blocked() -> None:
    fetcher = _fetcher(_page, {"intranet.example": ["192.168.1.10"]})
    with pytest.raises(FetchError) as info:
        await fetcher.fetch("https://intranet.example/", respect_robots=False)
    assert info.value.code == "blocked"


async def test_redirect_to_private_network_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://internal.example/secret"})
        return httpx.Response(200, text="secret")

    fetcher = _fetcher(handler, {"internal.example": ["10.1.2.3"]})
    with pytest.raises(FetchError) as info:
        await fetcher.fetch("https://example.com/", respect_robots=False)
    assert info.value.code == "blocked"


async def test_unsupported_content_type_and_size_limit() -> None:
    def binary(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/octet-stream"}, content=b"x"
        )

    with pytest.raises(FetchError) as info:
        await _fetcher(binary).fetch("https://example.com/f", respect_robots=False)
    assert info.value.code == "content_type"

    def huge(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, content=b"x" * (11 * 1024 * 1024)
        )

    with pytest.raises(FetchError) as info:
        await _fetcher(huge).fetch("https://example.com/big", respect_robots=False)
    assert info.value.code == "too_large"


async def test_robots_txt_is_respected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="ok")

    fetcher = _fetcher(handler)
    assert (await fetcher.fetch("https://example.com/public")).data == b"ok"
    with pytest.raises(FetchError) as info:
        await fetcher.fetch("https://example.com/private/page")
    assert info.value.code == "robots"


async def test_http_errors_are_readable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(FetchError) as info:
        await _fetcher(handler).fetch("https://example.com/missing", respect_robots=False)
    assert "404" in info.value.message
