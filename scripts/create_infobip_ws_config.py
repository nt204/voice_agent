from urllib.parse import urlencode, urljoin, urlparse, urlunparse

import httpx

from app.config import config, require_env


def websocket_url() -> str:
    public_base_url = require_env("PUBLIC_BASE_URL")
    parsed = urlparse(urljoin(public_base_url.rstrip("/") + "/", "infobip/ws"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = ""
    if config.infobip.ws_shared_secret:
        query = urlencode({"token": config.infobip.ws_shared_secret})
    return urlunparse((scheme, parsed.netloc, parsed.path, "", query, ""))


def main() -> None:
    base_url = require_env("INFOBIP_BASE_URL")
    api_key = require_env("INFOBIP_API_KEY")

    payload = {
        "type": "WEBSOCKET_ENDPOINT",
        "name": config.infobip.ws_config_name,
        "url": websocket_url(),
        "sampleRate": str(config.infobip.ws_sample_rate),
    }

    response = httpx.post(
        f"https://{base_url}/calls/1/media-stream-configs",
        headers={
            "Authorization": f"App {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if response.is_error:
        print("Failed to create Infobip WebSocket endpoint config")
        print(response.status_code)
        print(response.text)
        raise SystemExit(1)

    body = response.json()
    print("Created Infobip WebSocket endpoint config:")
    print(body)
    print(f"\nSet INFOBIP_WS_CONFIG_ID={body.get('id')}")


if __name__ == "__main__":
    main()
