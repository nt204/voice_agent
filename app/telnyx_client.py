from urllib.parse import urlencode

import httpx

from app.config import config, require_env


def create_outbound_call(to_number: str, from_number: str | None = None) -> dict:
    api_key = require_env("TELNYX_API_KEY")
    account_sid = require_env("TELNYX_ACCOUNT_SID")
    texml_app_id = require_env("TELNYX_TEXML_APP_ID")
    public_base_url = require_env("PUBLIC_BASE_URL").rstrip("/")
    caller = from_number or config.telnyx.from_number
    if not caller:
        raise RuntimeError("Missing TELNYX_FROM_NUMBER or from_number")

    answer_url = f"{public_base_url}/telnyx/answer?{urlencode({'direction': 'outbound-ai'})}"
    response = httpx.post(
        f"https://api.telnyx.com/v2/texml/Accounts/{account_sid}/Calls",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "ApplicationSid": texml_app_id,
            "To": to_number,
            "From": caller,
            "Url": answer_url,
            "MachineDetection": "Disable",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
