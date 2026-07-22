from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from app.config import BASE_DIR, config
from app.phone_numbers import normalize_phone_number


DEFAULT_OFFERS = (
    {
        "name": "Venus BigOne Combo 1",
        "quantity": 1,
        "unit_price": 120000,
        "total_price": 120000,
        "shipping_policy": "Standard delivery",
        "active": True,
    },
    {
        "name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "shipping_policy": "Free delivery",
        "active": True,
    },
    {
        "name": "Venus BigOne Combo 3",
        "quantity": 3,
        "unit_price": 130000,
        "total_price": 390000,
        "shipping_policy": "Free delivery",
        "active": True,
    },
    {
        "name": "Venus BigOne Combo 5",
        "quantity": 5,
        "unit_price": 126000,
        "total_price": 630000,
        "shipping_policy": "Free delivery",
        "active": True,
    },
)


def default_product_payload() -> dict[str, Any]:
    path = Path(config.gemini.product_knowledge_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    knowledge = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    return {
        "name": "Venus BigOne",
        "slug": "venus-bigone",
        "phone_number": normalize_phone_number(
            config.telnyx.outbound_from_number or ""
        ),
        "texml_app_id": config.telnyx.texml_app_id or "",
        "inbound_greeting": config.gemini.inbound_initial_greeting,
        "outbound_greeting": config.gemini.outbound_initial_greeting,
        "system_prompt": config.gemini.system_instruction,
        "knowledge": knowledge,
        "language_code": config.gemini.language_code,
        "voice_name": config.gemini.voice_name,
        "active": True,
        "is_default": True,
        "offers": [dict(offer) for offer in DEFAULT_OFFERS],
    }


def validate_product_payload(
    payload: Mapping[str, Any], *, allow_empty_phone: bool = False
) -> dict[str, Any]:
    name = _required_text(payload, "name", 160)
    slug = _slug(str(payload.get("slug") or name))
    phone_number = normalize_phone_number(str(payload.get("phone_number") or ""))
    if not phone_number and not allow_empty_phone:
        raise ValueError("Product phone number is required")

    offers = payload.get("offers") or []
    if not isinstance(offers, list):
        raise ValueError("Product offers must be a list")
    validated_offers = [validate_offer_payload(offer) for offer in offers]
    if not validated_offers:
        raise ValueError("Product must have at least one offer")
    if not any(offer["active"] for offer in validated_offers):
        raise ValueError("Product must have at least one active offer")
    offer_names = [offer["name"].casefold() for offer in validated_offers]
    if len(offer_names) != len(set(offer_names)):
        raise ValueError("Product offer names must be unique")
    active_quantities = [
        offer["quantity"] for offer in validated_offers if offer["active"]
    ]
    if len(active_quantities) != len(set(active_quantities)):
        raise ValueError("Active product offers must use unique quantities")

    return {
        "name": name,
        "slug": slug,
        "phone_number": phone_number,
        "texml_app_id": _text(payload.get("texml_app_id"), 160),
        "inbound_greeting": _required_text(payload, "inbound_greeting", 2000),
        "outbound_greeting": _required_text(payload, "outbound_greeting", 2000),
        "system_prompt": _required_text(payload, "system_prompt", 12000),
        "knowledge": _required_text(payload, "knowledge", 50000),
        "language_code": _text(payload.get("language_code") or "my-MM", 20),
        "voice_name": _text(payload.get("voice_name") or "Aoede", 80),
        "active": bool(payload.get("active", True)),
        "offers": validated_offers,
    }


def validate_offer_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Each offer must be an object")
    quantity = _positive_int(payload.get("quantity"), "Offer quantity")
    unit_price = _positive_int(payload.get("unit_price"), "Offer unit price")
    total_price = _positive_int(payload.get("total_price"), "Offer total price")
    return {
        "name": _required_text(payload, "name", 200),
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "shipping_policy": _text(payload.get("shipping_policy"), 500),
        "active": bool(payload.get("active", True)),
    }


def product_knowledge_text(product: Mapping[str, Any]) -> str:
    sections = [
        f"Product: {str(product.get('name') or '').strip()}",
        str(product.get("knowledge") or "").strip(),
    ]
    active_offers = [offer for offer in product.get("offers") or [] if offer.get("active", True)]
    if active_offers:
        offer_lines = ["Offers and authoritative prices:"]
        for offer in active_offers:
            offer_lines.append(
                "- {name}: quantity={quantity}, unit_price={unit_price} MMK, "
                "total_price={total_price} MMK, shipping={shipping}".format(
                    name=offer.get("name", ""),
                    quantity=offer.get("quantity", 0),
                    unit_price=offer.get("unit_price", 0),
                    total_price=offer.get("total_price", 0),
                    shipping=offer.get("shipping_policy") or "not specified",
                )
            )
        sections.append("\n".join(offer_lines))
    return "\n\n".join(section for section in sections if section).strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError("Product slug must contain letters or numbers")
    return slug[:100]


def _required_text(payload: Mapping[str, Any], field: str, limit: int) -> str:
    value = _text(payload.get(field), limit)
    if not value:
        raise ValueError(f"Product {field.replace('_', ' ')} is required")
    return value


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _positive_int(value: Any, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return parsed
