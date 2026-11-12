"""Login and cookie import tests."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from curl_cffi import Response

from dlsite_async.api import DlsiteAPI
from dlsite_async.exceptions import AuthenticationError


_LOGIN_FORM = '<html><body><input name="_token" value="tok123"></body></html>'


def _response(url: str, text: str = "") -> MagicMock:
    response = MagicMock(spec=Response)
    response.url = url
    response.text = text
    return response


async def test_login_oauth_handoff(api: DlsiteAPI) -> None:
    """login() starts from oauth2/auth and succeeds when landing on www."""
    get = AsyncMock(return_value=_response("https://login.dlsite.com/login", _LOGIN_FORM))
    post = AsyncMock(return_value=_response("https://www.dlsite.com/aix/login"))
    with (
        patch.object(api.session, "get", get),
        patch.object(api.session, "post", post),
    ):
        await api.login("user", "pass", site_id="aix")
    assert api._authed  # noqa: SLF001
    assert get.await_args is not None
    assert get.await_args.args[0] == "https://login.dlsite.com/oauth2/auth"
    params = get.await_args.kwargs["params"]
    assert params["redirect_uri"] == "https://www.dlsite.com/aix/login"
    assert params["cancel_uri"] == "https://www.dlsite.com/aix/"
    assert params["state"]
    assert post.await_args is not None
    assert post.await_args.args[0] == "https://login.dlsite.com/login"
    assert post.await_args.kwargs["data"] == {
        "_token": "tok123",
        "login_id": "user",
        "password": "pass",
    }


async def test_login_default_site_id(api: DlsiteAPI) -> None:
    """site_id defaults to maniax."""
    get = AsyncMock(return_value=_response("https://login.dlsite.com/login", _LOGIN_FORM))
    post = AsyncMock(return_value=_response("https://www.dlsite.com/maniax/login"))
    with (
        patch.object(api.session, "get", get),
        patch.object(api.session, "post", post),
    ):
        await api.login("user", "pass")
    assert get.await_args is not None
    params = get.await_args.kwargs["params"]
    assert params["redirect_uri"] == "https://www.dlsite.com/maniax/login"


async def test_login_failed(api: DlsiteAPI) -> None:
    """login() fails when the credential POST never reaches www.dlsite.com."""
    get = AsyncMock(return_value=_response("https://login.dlsite.com/login", _LOGIN_FORM))
    post = AsyncMock(return_value=_response("https://login.dlsite.com/login"))
    with (
        patch.object(api.session, "get", get),
        patch.object(api.session, "post", post),
        pytest.raises(AuthenticationError),
    ):
        await api.login("user", "pass")
    assert not api._authed  # noqa: SLF001


async def test_login_requires_credentials(api: DlsiteAPI) -> None:
    """login() fails without credentials (and no netrc entry)."""
    with (
        patch("dlsite_async.api.netrc", side_effect=FileNotFoundError),
        pytest.raises(AuthenticationError),
    ):
        await api.login()


async def test_init_kwargs_and_cookies() -> None:
    """DlsiteAPI forwards kwargs and merges extra cookies."""
    async with DlsiteAPI(cookies={"extra": "1"}, timeout=5) as api:
        cookies = api.session.cookies.get_dict()
        assert cookies["adultchecked"] == "1"
        assert cookies["extra"] == "1"


async def test_load_cookies_txt(api: DlsiteAPI, tmp_path: Path) -> None:
    """load_cookies_txt() imports Netscape cookies, skipping comments/junk."""
    path = tmp_path / "cookies.txt"
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        "\n"
        ".dlsite.com\tTRUE\t/\tTRUE\t0\tsess\tabc\n"
        "login.dlsite.com\tFALSE\t/\tFALSE\t0\tother\tdef\n"
        "malformed line\n",
        encoding="utf-8",
    )
    api.load_cookies_txt(path)
    by_name = {c.name: c for c in api.session.cookies.jar}
    assert by_name["sess"].value == "abc"
    assert by_name["sess"].domain == ".dlsite.com"
    assert by_name["sess"].secure
    assert by_name["other"].value == "def"
    assert by_name["other"].domain == "login.dlsite.com"
    assert not by_name["other"].secure
    assert len(by_name) == 3  # adultchecked + the two imported cookies

