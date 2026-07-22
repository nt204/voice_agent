"""Resolve package counts from Sheet campaigns against configured offers."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


MYANMAR_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")


def _normalized_offer_name(value: object) -> str:
    text = str(value or "").translate(MYANMAR_DIGITS).casefold()
    return re.sub(r"[^a-z0-9\u1000-\u109f]+", " ", text).strip()


def positive_package_count(value: object) -> int | None:
    text = str(value or "").translate(MYANMAR_DIGITS).strip()
    match = re.fullmatch(r"[0-9]+", text)
    if not match:
        return None
    count = int(text)
    return count if 1 <= count <= 100 else None


def active_offers(product: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not product:
        return []
    return [
        dict(offer)
        for offer in product.get("offers") or []
        if isinstance(offer, Mapping) and offer.get("active", True)
    ]


def match_configured_offer(
    requested_offer: object,
    offers: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    requested = _normalized_offer_name(requested_offer)
    if not requested:
        return None

    exact = [
        dict(offer)
        for offer in offers
        if offer.get("active", True)
        and _normalized_offer_name(offer.get("name")) == requested
    ]
    if len(exact) == 1:
        return exact[0]

    contained = []
    for offer in offers:
        if not offer.get("active", True):
            continue
        name = _normalized_offer_name(offer.get("name"))
        if name and (name in requested or requested in name):
            contained.append(dict(offer))
    return contained[0] if len(contained) == 1 else None


def resolved_campaign_order(
    lead_info: Mapping[str, Any],
    product: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve Sheet Qty as package count, never as units inside an offer."""
    # Some Sheets put the configured combo name in a generic "Product"
    # column instead of a dedicated "Combo/Offer" column. Matching still has
    # to be against the selected product's active offers, so this fallback
    # cannot switch the campaign to an unrelated product.
    requested_offer = str(
        lead_info.get("offer") or lead_info.get("product") or ""
    ).strip()
    package_count = positive_package_count(lead_info.get("quantity"))
    offer = match_configured_offer(requested_offer, active_offers(product))
    if not offer or package_count is None:
        return {}

    units_per_package = int(offer.get("quantity") or 0)
    unit_price = int(offer.get("unit_price") or 0)
    package_price = int(offer.get("total_price") or 0)
    if units_per_package <= 0 or package_price <= 0:
        return {}

    return {
        "offer_name": str(offer.get("name") or requested_offer).strip(),
        "package_count": package_count,
        "units_per_package": units_per_package,
        "total_units": units_per_package * package_count,
        "unit_price": unit_price,
        "package_price": package_price,
        "total_price": package_price * package_count,
    }
