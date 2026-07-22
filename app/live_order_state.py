from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
import re
from typing import Any

from google.genai import types

from app.campaign_order import match_configured_offer, positive_package_count
from app.sales_analysis import (
    _extract_phone_precise,
    _is_clearly_non_myanmar_address,
    _looks_like_address,
)


DELIVERY_STATE_FUNCTION = "update_delivery_state"
PHONE_KEYPAD_FALLBACK_FAILURES = 3


AMBIGUOUS_RECIPIENT_NAMES = {
    "မမ",
    "customer",
    "customer name",
    "khach hang",
    "khách hàng",
    "chị",
    "chi",
    "cô",
    "co",
    "anh",
}


def delivery_state_tool() -> types.Tool:
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=DELIVERY_STATE_FUNCTION,
                description=(
                    "Store or confirm one campaign order/delivery field. Call this whenever "
                    "the customer provides, corrects, accepts, or rejects an offer, package "
                    "count, recipient name, phone number, or shipping address. A set action "
                    "always replaces the previous value for that field."
                ),
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": [
                                "offer",
                                "package_count",
                                "customer_name",
                                "phone",
                                "shipping_address",
                            ],
                        },
                        "action": {
                            "type": "string",
                            "enum": ["set", "confirm", "reject"],
                        },
                        "value": {
                            "type": "string",
                            "description": (
                                "The complete replacement value for set. Never send a "
                                "partial phone number or combine separate attempts."
                            ),
                        },
                    },
                    "required": ["field", "action"],
                },
            )
        ]
    )


def _phone_for_readback(value: str) -> str:
    candidate = _extract_phone_precise(value)
    if not candidate:
        return ""
    digits = "".join(char for char in candidate if char.isdigit())
    if candidate.startswith("+95") and digits.startswith("95"):
        return f"0{digits[2:]}"
    if not candidate.startswith("+") and digits.startswith("959"):
        return f"0{digits[2:]}"
    return digits


def _clean_address(value: str) -> str:
    return str(value or "").strip(" \t\r\n,.;:-။၊")


def clean_recipient_name(value: str) -> str:
    candidate = str(value or "").strip(" \t\r\n,.;:-။၊")
    folded = re.sub(r"\s+", " ", candidate.casefold())
    if (
        not 2 <= len(candidate) <= 80
        or folded in AMBIGUOUS_RECIPIENT_NAMES
        or re.search(r"\d", candidate)
        or not re.search(r"[A-Za-zÀ-ỹ\u1000-\u109F]", candidate)
    ):
        return ""
    return candidate


@dataclass
class LiveDeliveryState:
    connected_phone: str = ""
    require_customer_name: bool = False
    require_order_confirmation: bool = False
    configured_offers: list[dict[str, Any]] = dataclass_field(default_factory=list)
    offer_name: str = ""
    offer_confirmed: bool = False
    package_count: int | None = None
    package_count_confirmed: bool = False
    units_per_package: int = 0
    unit_price: int = 0
    package_price: int = 0
    customer_name: str = ""
    name_confirmed: bool = False
    phone: str = ""
    phone_confirmed: bool = False
    shipping_address: str = ""
    address_confirmed: bool = False
    phone_failures: int = 0
    phone_rejections: int = 0
    name_failures: int = 0
    address_failures: int = 0

    def apply(self, *, field: str, action: str, value: str = "") -> dict[str, Any]:
        if field not in {
            "offer",
            "package_count",
            "customer_name",
            "phone",
            "shipping_address",
        }:
            return self._response(False, "Unsupported delivery field.")
        if action not in {"set", "confirm", "reject"}:
            return self._response(False, "Unsupported delivery state action.")

        if action == "set":
            return self._set(field, value)
        if action == "confirm":
            return self._confirm(field)
        return self._reject(field)

    def confirmed_facts(self) -> dict[str, str]:
        return {
            "customer_name": self.customer_name if self.name_confirmed else "",
            "phone": self.phone if self.phone_confirmed else "",
            "shipping_address": (
                self.shipping_address if self.address_confirmed else ""
            ),
        }

    def confirmed_order_facts(self) -> dict[str, Any]:
        if not (
            self.offer_confirmed
            and self.package_count_confirmed
            and self.offer_name
            and self.package_count
            and self.units_per_package > 0
            and self.package_price > 0
        ):
            return {}
        return {
            "offer_name": self.offer_name,
            "package_count": self.package_count,
            "units_per_package": self.units_per_package,
            "total_units": self.units_per_package * self.package_count,
            "unit_price": self.unit_price,
            "package_price": self.package_price,
            "total_price": self.package_price * self.package_count,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "connected_phone": self.connected_phone,
            "require_customer_name": self.require_customer_name,
            "require_order_confirmation": self.require_order_confirmation,
            "offer_name": self.offer_name,
            "offer_confirmed": self.offer_confirmed,
            "package_count": self.package_count,
            "package_count_confirmed": self.package_count_confirmed,
            "units_per_package": self.units_per_package,
            "customer_name": self.customer_name,
            "name_confirmed": self.name_confirmed,
            "phone": self.phone,
            "phone_confirmed": self.phone_confirmed,
            "shipping_address": self.shipping_address,
            "address_confirmed": self.address_confirmed,
        }

    def status_response(self, *, ok: bool, message: str) -> dict[str, Any]:
        return self._response(ok, message)

    def _set(self, field: str, value: str) -> dict[str, Any]:
        if field == "offer":
            self.offer_name = ""
            self.offer_confirmed = False
            self.units_per_package = 0
            self.unit_price = 0
            self.package_price = 0
            offer = match_configured_offer(value, self.configured_offers)
            if not offer:
                return self._response(False, "The offer is not an active configured offer.")
            self.offer_name = str(offer.get("name") or "").strip()
            self.units_per_package = int(offer.get("quantity") or 0)
            self.unit_price = int(offer.get("unit_price") or 0)
            self.package_price = int(offer.get("total_price") or 0)
            return self._response(True, "Configured offer candidate replaced.")

        if field == "package_count":
            self.package_count = None
            self.package_count_confirmed = False
            count = positive_package_count(value)
            if count is None:
                return self._response(False, "The package/combo count is invalid.")
            self.package_count = count
            return self._response(True, "Package/combo count candidate replaced.")

        if field == "customer_name":
            self.customer_name = ""
            self.name_confirmed = False
            candidate = clean_recipient_name(value)
            if not candidate:
                self.name_failures += 1
                return self._response(False, "The recipient name is missing or ambiguous.")
            self.customer_name = candidate
            return self._response(True, "Recipient name candidate replaced.")

        if field == "phone":
            # A new attempt invalidates the old candidate even when this attempt is partial.
            self.phone = ""
            self.phone_confirmed = False
            candidate = _phone_for_readback(value)
            if not candidate:
                self.phone_failures += 1
                return self._response(False, "The phone number is incomplete or invalid.")
            self.phone = candidate
            return self._response(True, "Phone candidate replaced.")

        self.shipping_address = ""
        self.address_confirmed = False
        candidate = _clean_address(value)
        if (
            not _looks_like_address(candidate)
            or _is_clearly_non_myanmar_address(candidate)
        ):
            self.address_failures += 1
            return self._response(False, "The shipping address is unclear or outside Myanmar.")
        self.shipping_address = candidate
        return self._response(True, "Shipping address candidate replaced.")

    def _confirm(self, field: str) -> dict[str, Any]:
        if field == "offer":
            if not self.offer_name:
                return self._response(False, "There is no configured offer to confirm.")
            self.offer_confirmed = True
            return self._response(True, "Configured offer confirmed by the customer.")

        if field == "package_count":
            if not self.package_count:
                return self._response(False, "There is no package/combo count to confirm.")
            self.package_count_confirmed = True
            return self._response(True, "Package/combo count confirmed by the customer.")

        if field == "customer_name":
            if not self.customer_name:
                return self._response(False, "There is no recipient name to confirm.")
            self.name_confirmed = True
            return self._response(True, "Recipient name confirmed by the customer.")

        if field == "phone":
            if not self.phone:
                return self._response(False, "There is no phone candidate to confirm.")
            self.phone_confirmed = True
            return self._response(True, "Phone confirmed by the customer.")

        if not self.shipping_address:
            return self._response(False, "There is no address candidate to confirm.")
        self.address_confirmed = True
        return self._response(True, "Shipping address confirmed by the customer.")

    def _reject(self, field: str) -> dict[str, Any]:
        if field == "offer":
            self.offer_name = ""
            self.offer_confirmed = False
            self.units_per_package = 0
            self.unit_price = 0
            self.package_price = 0
            return self._response(True, "Rejected offer cleared.")

        if field == "package_count":
            self.package_count = None
            self.package_count_confirmed = False
            return self._response(True, "Rejected package/combo count cleared.")

        if field == "customer_name":
            self.customer_name = ""
            self.name_confirmed = False
            self.name_failures += 1
            return self._response(True, "Rejected recipient name cleared.")

        if field == "phone":
            self.phone = ""
            self.phone_confirmed = False
            self.phone_failures += 1
            self.phone_rejections += 1
            return self._response(True, "Rejected phone candidate cleared.")

        self.shipping_address = ""
        self.address_confirmed = False
        self.address_failures += 1
        return self._response(True, "Rejected address candidate cleared.")

    def _response(self, ok: bool, message: str) -> dict[str, Any]:
        next_action, instruction = self._next_action()
        return {
            "ok": ok,
            "message": message,
            "state": self.snapshot(),
            "next_action": next_action,
            "instruction": instruction,
        }

    def _next_action(self) -> tuple[str, str]:
        if self.require_order_confirmation and not self.offer_name:
            names = ", ".join(
                str(offer.get("name") or "").strip()
                for offer in self.configured_offers
                if str(offer.get("name") or "").strip()
            )
            return (
                "ask_offer",
                f"Ask which configured offer is required. Active offers: {names}.",
            )
        if self.require_order_confirmation and not self.package_count:
            return (
                "ask_package_count",
                "Ask how many packages/combos the customer wants. This is not the unit count inside one package.",
            )
        if self.require_order_confirmation and not (
            self.offer_confirmed and self.package_count_confirmed
        ):
            total_units = self.units_per_package * int(self.package_count or 0)
            total_price = self.package_price * int(self.package_count or 0)
            return (
                "confirm_offer_and_package_count",
                "Read back and confirm together: "
                f"{self.package_count} package(s) of {self.offer_name}, "
                f"{self.units_per_package} unit(s) per package, {total_units} total "
                f"product units, total price {total_price} MMK. On acceptance confirm "
                "both field=offer and field=package_count separately.",
            )
        if self.require_customer_name and not self.customer_name:
            return (
                "ask_customer_name",
                "Ask only for the recipient's complete name. Do not reuse the rejected or ambiguous Sheet name.",
            )
        if self.require_customer_name and not self.name_confirmed:
            return (
                "confirm_customer_name",
                f"Read back this recipient name exactly: {self.customer_name}. Ask only whether it is correct.",
            )
        if not self.phone:
            if self.phone_rejections >= 1:
                return (
                    "collect_phone_by_keypad",
                    "The customer rejected the first phone readback. Ask them to enter the complete delivery phone number on the keypad and press #. Do not accept another spoken replacement.",
                )
            if self.phone_failures >= PHONE_KEYPAD_FALLBACK_FAILURES:
                return (
                    "collect_phone_by_keypad",
                    "The spoken phone number has failed three times. Ask the customer to enter the complete phone number on the keypad and press #. If they cannot use the keypad, ask them to say the full number slowly one more time.",
                )
            return (
                "ask_phone",
                "Ask for one complete phone number from the beginning, spoken slowly one digit at a time. Do not reuse any old digits.",
            )
        if not self.phone_confirmed:
            digits = " ".join(self.phone)
            return (
                "confirm_phone",
                f"Read back these digits one by one: {digits}. Ask only whether they are correct.",
            )
        if not self.shipping_address:
            return (
                "ask_shipping_address",
                "Ask only for the complete Myanmar shipping address again. The rejected address is invalid and must never be reused.",
            )
        if not self.address_confirmed:
            return (
                "confirm_shipping_address",
                f"Read back this exact address: {self.shipping_address}. Ask only whether it is correct.",
            )
        return (
            "read_back_order",
            "The required delivery fields are confirmed. Read back the complete order once using only the latest values and ask for final order confirmation.",
        )
