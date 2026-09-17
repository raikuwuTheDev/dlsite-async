"""DLsite API classes."""

import secrets
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from dataclasses import replace
from datetime import datetime
from http.cookies import SimpleCookie
from netrc import netrc
from pathlib import Path
from typing import Any, TypeVar

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client import _RequestContextManager
from yarl import URL

from ._scraper import parse_circle_html, parse_login_token, parse_work_html
from .circle import Circle
from .exceptions import AuthenticationError, DlsiteError
from .work import AgeCategory, BookType, Work, WorkType


_T = TypeVar("_T")


def _datetime_from_timestamp(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")


class BaseAPI(AbstractAsyncContextManager["_T"]):
    """Base DLsite API session.

    Args:
        kwargs: Keyword args to pass into aiohttp.ClientSession.
    """

    _DL_CHUNK_SIZE = 1024 * 1024
    _DL_TIMEOUT = ClientTimeout(
        total=None,
        connect=300,
        sock_connect=None,
        sock_read=None,
    )

    def __init__(self, **kwargs: Any):
        self._exit_stack = AsyncExitStack()
        kwargs["raise_for_status"] = True
        self.session = ClientSession(**kwargs)
        self._exit_stack.push_async_exit(self.session)
        self._authed = False

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close this API session."""
        async with self._exit_stack:
            pass

    def get(self, *args: Any, **kwargs: Any) -> _RequestContextManager:
        """Perform get request."""
        return self.session.get(*args, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> _RequestContextManager:
        """Perform post request."""
        return self.session.post(*args, **kwargs)

    def load_cookies_txt(self, path: str | Path) -> None:
        """Load cookies from a Netscape-format cookies.txt file.

        Some login flows (e.g. DLsite's ``aix`` floor) sit behind
        bot-detection that a plain HTTP client cannot pass, even once the
        request logic matches a real browser exactly. In that case, log in
        once using a real browser and export its cookies for the target
        domain(s) with a browser extension (e.g. "Get cookies.txt LOCALLY"),
        then load that export here before making any requests.

        Args:
            path: Path to a Netscape-format cookies.txt file.
        """
        by_domain: dict[str, SimpleCookie] = {}
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) != 7:
                    continue
                domain, _flag, cookie_path, secure, _expiration, name, value = fields
                cookie = by_domain.setdefault(domain.lstrip("."), SimpleCookie())
                cookie[name] = value
                cookie[name]["domain"] = domain
                cookie[name]["path"] = cookie_path
                if secure == "TRUE":
                    cookie[name]["secure"] = True
        for domain, cookie in by_domain.items():
            self.session.cookie_jar.update_cookies(
                cookie, response_url=URL(f"https://{domain}/")
            )

    async def login(
        self,
        login_id: str | None = None,
        password: str | None = None,
        netrc_host: str = "dlsite.com",
        site_id: str = "maniax",
    ) -> None:
        """Login to DLsite.

        Args:
            login_id: DLsite login ID.
            password: DLsite password.
            netrc_host: Optional .netrc host. If `login_id` or `password` are
                not set, they will be read from the specfied .netrc entry.
            site_id: DLsite floor to complete the SSO handoff for (e.g.
                ``"maniax"`` or ``"aix"``). Authenticating against
                ``login.dlsite.com`` alone only sets cookies on that domain;
                without this follow-up step ``www.dlsite.com`` (where product
                pages actually live) never sees a valid session and content
                gated behind login (such as the ``aix`` floor) stays hidden.

        Raises:
            AuthenticationError: Login failed.

        Note:
            Social media logins are unsupported.
        """
        if not login_id or not password:
            try:
                authenticator = netrc().authenticators(netrc_host)
                if authenticator is not None:
                    login_id, _, password = authenticator
            except FileNotFoundError:
                pass
        if not login_id or not password:
            raise AuthenticationError("DLsite login_id and password are required.")
        # Visiting the OAuth2 authorize endpoint first (while unauthenticated)
        # establishes the pending authorization request that the login form
        # is bound to. Logging in without this step only authenticates the
        # login.dlsite.com SSO session; the credential POST then has no
        # pending OAuth request to complete and never hands a session back to
        # www.dlsite.com (where product pages, including gated floors like
        # aix, are actually served from).
        url = "https://login.dlsite.com/login"
        oauth_url = "https://login.dlsite.com/oauth2/auth"
        oauth_params = {
            "client_id": "dlsite.user",
            "redirect_uri": f"https://www.dlsite.com/{site_id}/login",
            "cancel_uri": f"https://www.dlsite.com/{site_id}/",
            "response_type": "code",
            "state": secrets.token_hex(16),
        }
        async with self.get(oauth_url, params=oauth_params) as response:
            content = await response.text()
            token = parse_login_token(content)
        payload = {
            "_token": token,
            "login_id": login_id,
            "password": password,
        }
        async with self.post(url, data=payload) as response:
            if response.url.host != "www.dlsite.com":
                raise AuthenticationError("DLsite login failed.")
        self._authed = True


_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


class DlsiteAPI(BaseAPI["DlsiteAPI"]):
    """DLsite API session.

    Args:
        locale: Optional locale. Defaults to ``ja_JP``.
        kwargs: Keyword args to pass into aiohttp.ClientSession (e.g.
            ``connector`` to route requests through a proxy).
    """

    def __init__(self, locale: str | None = None, **kwargs: Any):
        headers = {**_DEFAULT_HEADERS, **kwargs.pop("headers", {})}
        cookies = {"adultchecked": "1", **kwargs.pop("cookies", {})}
        super().__init__(cookies=cookies, headers=headers, **kwargs)
        self.locale = locale

    @property
    def _common_params(self) -> dict[str, str]:
        return {"locale": self.locale} if self.locale else {}

    def get(self, *args: Any, **kwargs: Any) -> _RequestContextManager:
        """Perform get request."""
        if "params" in kwargs:
            kwargs["params"].update(self._common_params)
        else:
            kwargs["params"] = self._common_params
        return super().get(*args, **kwargs)

    async def get_work(self, product_id: str) -> Work:
        """Return the specified work.

        Args:
            product_id: DLsite product ID.

        Returns:
            Complete work information.
        """
        work = await self.product_info(product_id)
        return await self._fill_work_details(work)

    async def product_info(self, product_id: str) -> Work:
        """Return ajax API product info.

        Args:
            product_id: DLsite product ID.

        Returns:
            Minimal product information.

        Raises:
            DlsiteError: Failed to get product info.
        """
        url = "https://www.dlsite.com/maniax/product/info/ajax"
        params = {"product_id": product_id}
        async with self.get(url, params=params) as response:
            data = await response.json()
        if not data or product_id not in data:
            raise DlsiteError(f"Failed to get product info for {product_id}")
        info = data[product_id]
        info["product_id"] = product_id
        info["age_category"] = AgeCategory(info["age_category"])
        info["work_type"] = WorkType(info["work_type"])
        if info.get("book_type"):
            info["book_type"] = BookType(info["book_type"]["value"])
        if info.get("regist_date"):
            info["regist_date"] = _datetime_from_timestamp(info["regist_date"])
        return Work.from_dict(info)

    async def _fill_work_details(self, work: Work) -> Work:
        html = await self._fetch_work_html(work)
        if not html:
            return work
        details = parse_work_html(html)
        return replace(work, **details)

    async def _fetch_work_html(self, work: Work) -> str | None:
        urls = [
            (
                f"https://www.dlsite.com/{work.site_id}/{typ}"
                f"/=/product_id/{work.product_id}.html/"
            )
            for typ in ("work", "announce")
        ]
        html: str | None = None
        for url in urls:
            async with self.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    break
        return html

    async def get_circle(self, maker_id: str) -> Circle:
        """Return the specified circle.

        Args:
            maker_id: DLsite maker ID.

        Returns:
            Circle information.

        Raises:
            DlsiteError: Failed to fetch circle information.
        """
        html = await self._fetch_circle_html(maker_id)
        if not html:
            raise DlsiteError(f"Failed to get circle {maker_id}")
        info = parse_circle_html(html)
        info["maker_id"] = maker_id
        return Circle.from_dict(info)

    async def _fetch_circle_html(self, maker_id: str) -> str | None:
        url = (
            f"https://www.dlsite.com/maniax/circle/profile/=/maker_id/{maker_id}.html/"
        )
        async with self.get(url) as response:
            if response.status == 200:
                return await response.text()
        return None
