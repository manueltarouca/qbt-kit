"""The `app` scope — 16 endpoints on 5.2.3, 9 on 4.4.5.

Half of this scope is newer than the compatibility floor: cookies, API-key
management, directory browsing, process info and test email all arrived after
4.4.5, so each carries a `since` taken from the inventory diffs.
"""

from __future__ import annotations

from ._types import (
    Body,
    Endpoint,
    Json,
    NoContent,
    Param,
    RawText,
    Wire,
    flag,
    register,
    text,
)

# Writing any of these severs the caller's own connection or weakens the
# server's security posture. The MCP layer refuses them outright and the CLI
# warns; a model nudging `web_ui_password` would lock the user out of their own
# client.
LOCKOUT_KEYS = frozenset(
    {
        "web_ui_username",
        "web_ui_password",
        "web_ui_port",
        "web_ui_address",
        "web_ui_domain_list",
        "use_https",
        "bypass_local_auth",
        "bypass_auth_subnet_whitelist",
        "bypass_auth_subnet_whitelist_enabled",
        "web_ui_host_header_validation_enabled",
        "web_ui_csrf_protection_enabled",
        "web_ui_clickjacking_protection_enabled",
        "web_ui_secure_cookie_enabled",
        "web_ui_max_auth_fail_count",
        "web_ui_ban_duration",
        "alternative_webui_enabled",
        "alternative_webui_path",
        # Reachability: UPnP forwards the WebUI off the LAN, and a reverse-proxy
        # trust list lets a forged X-Forwarded-For defeat IP bans and the subnet
        # whitelist.
        "web_ui_upnp",
        "web_ui_reverse_proxy_enabled",
        "web_ui_reverse_proxies_list",
        # Pointing HTTPS at a missing or unreadable file locks you out as surely
        # as changing the port.
        "web_ui_https_cert_path",
        "web_ui_https_key_path",
        "web_ui_custom_http_headers",
        "web_ui_use_custom_http_headers_enabled",
        # Arbitrary command execution on torrent events. This is the single
        # worst thing an agent could be talked into doing through this API, and
        # nothing legitimate about managing torrents needs to write it.
        "autorun_enabled",
        "autorun_program",
        "autorun_on_torrent_added_enabled",
        "autorun_on_torrent_added_program",
    }
)

register(
    Endpoint(
        scope="app",
        name="version",
        method="GET",
        summary="qBittorrent's own version, e.g. v5.2.3.",
        returns=RawText,
    ),
    Endpoint(
        scope="app",
        name="webapiVersion",
        method="GET",
        summary="WebAPI version, e.g. 2.15.1. Requires a session: measured 403 "
        "unauthenticated on every tested version, so this cannot be used "
        "to decide how to authenticate.",
        returns=RawText,
    ),
    Endpoint(
        scope="app",
        name="buildInfo",
        method="GET",
        since=(2, 3, 0),
        summary="Qt, libtorrent, boost, OpenSSL and zlib versions.",
        returns=Json("BuildInfo"),
    ),
    Endpoint(
        scope="app",
        name="defaultSavePath",
        method="GET",
        summary="The configured default save path.",
        returns=RawText,
    ),
    Endpoint(
        scope="app",
        name="preferences",
        method="GET",
        summary="All application preferences as one nested object.",
        returns=Json("Preferences"),
    ),
    Endpoint(
        scope="app",
        name="setPreferences",
        method="POST",
        summary="Write preferences. Takes a JSON object in the `json` form field; "
        "unknown keys pass through untouched rather than being dropped.",
        returns=NoContent,
        body=Body.URLENCODED,
        params=(
            Param(
                "json",
                Wire.JSON_BLOB,
                required=True,
                summary="object of preference keys to set",
                blocklist=LOCKOUT_KEYS,
            ),
        ),
        mutating=True,
    ),
    Endpoint(
        scope="app",
        name="shutdown",
        method="POST",
        summary="Shut qBittorrent down. There is no corresponding start.",
        returns=NoContent,
        mutating=True,
        destructive=True,
        untestable="terminates the server under test",
    ),
    # ----- newer than the floor
    Endpoint(
        scope="app",
        name="getDirectoryContent",
        method="GET",
        since=(2, 9, 3),
        summary="List a directory on the server's filesystem. Useful for "
        "validating a save path before setting it.",
        returns=Json("DirectoryEntry"),
        params=(text("dirPath", required=True), flag("withSymlinks")),
    ),
    Endpoint(
        scope="app",
        name="processInfo",
        method="GET",
        since=(2, 11, 3),
        summary="Process statistics. On 5.2.3 this is just `launch_time` — "
        "measured, not assumed from the field name.",
        returns=Json("ProcessInfo"),
    ),
    Endpoint(
        scope="app",
        name="cookies",
        method="GET",
        since=(2, 11, 2),
        summary="Cookies qBittorrent sends when fetching .torrent URLs.",
        returns=Json("Cookie"),
    ),
    Endpoint(
        scope="app",
        name="setCookies",
        method="POST",
        since=(2, 11, 2),
        summary="Replace the stored cookie list. JSON in a form field.",
        returns=NoContent,
        body=Body.URLENCODED,
        params=(Param("cookies", Wire.JSON_BLOB, required=True),),
        mutating=True,
    ),
    Endpoint(
        scope="app",
        name="rotateAPIKey",
        method="POST",
        since=(2, 15, 0),
        summary='Generate a new API key, returned as {"apiKey": …}. Invalidates '
        "the previous key, so a client authenticating with Bearer will "
        "lose access until it stores the new one.",
        returns=Json("ApiKey"),
        mutating=True,
        destructive=True,
    ),
    Endpoint(
        scope="app",
        name="deleteAPIKey",
        method="POST",
        since=(2, 15, 0),
        summary="Delete the API key, disabling Bearer authentication.",
        returns=NoContent,
        mutating=True,
        destructive=True,
    ),
    Endpoint(
        scope="app",
        name="sendTestEmail",
        method="POST",
        since=(2, 10, 4),
        summary="Send a test notification email.",
        returns=NoContent,
        mutating=True,
        untestable="needs an SMTP server",
    ),
    Endpoint(
        scope="app",
        name="networkInterfaceList",
        method="GET",
        since=(2, 3, 0),
        summary="Network interfaces qBittorrent can bind to.",
        returns=Json("NetworkInterface"),
    ),
    Endpoint(
        scope="app",
        name="networkInterfaceAddressList",
        method="GET",
        since=(2, 3, 0),
        summary="Addresses available on one interface.",
        returns=Json("InterfaceAddress"),
        params=(text("iface"),),
    ),
)
