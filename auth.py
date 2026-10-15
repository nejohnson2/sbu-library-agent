"""OAuth login for the NEXUS MCP server (SBU SSO happens on Clarivate's login page)."""

import json
from urllib.parse import urlsplit
from urllib.request import urlopen

from fastmcp.client.auth import OAuth
from key_value.aio.stores.keyring import KeyringStore
from mcp.shared.auth import OAuthMetadata


def make_auth(mcp_url: str) -> OAuth:
    """Browser login the first time; after that the token is saved in the macOS Keychain
    and refreshed automatically."""
    auth = OAuth(
        mcp_url,
        client_name="Nexus Agent",
        token_storage=KeyringStore(service_name="nexus-agent"),
        callback_port=8765,  # fixed, so the registered redirect URL stays valid
    )
    # Workaround for an MCP library bug: it only learns the real token URL during a full
    # login, so refreshing a saved token in a new process goes to the wrong address.
    # Looking the settings up here lets the refresh work without logging in again.
    auth.context.oauth_metadata = fetch_oauth_metadata(mcp_url)
    return auth


def fetch_oauth_metadata(mcp_url: str) -> OAuthMetadata:
    """Find the server's OAuth settings (token URL etc.) using the standard MCP discovery steps."""
    url = urlsplit(mcp_url)
    origin = f"{url.scheme}://{url.netloc}"
    resource = json.load(urlopen(f"{origin}/.well-known/oauth-protected-resource{url.path}"))
    issuer_path = urlsplit(resource["authorization_servers"][0]).path
    return OAuthMetadata.model_validate_json(
        urlopen(f"{origin}/.well-known/oauth-authorization-server{issuer_path}").read()
    )
