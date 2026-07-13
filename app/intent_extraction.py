from __future__ import annotations

import json
import re
from datetime import datetime

from google import genai
from google.genai import types
from sqlalchemy import desc, select

from app.config import config, require_env
from app.database import CallIntentRow, CallRecordingRow, CallTranscriptRow, db_session
from app.logging_utils import log


EXTRACTION_PROMPT = """You extract order details from customer call transcripts.

Rules:
- Return JSON only.
- Do not guess, infer, normalize, complete, or invent any field.
- Use only information explicitly stated by the customer, not the assistant.
- If a field is unclear, absent, or only implied, set it to null.
- order_intent is true only if the customer clearly says they want to buy/order/take a product.
- quantity is an integer only if the customer clearly states a count.
- combo is the exact bundle/combo wording only if explicitly stated.
- confidence must be 0.0 to 1.0 and should be low when transcript is ambiguous.
- missing_fields should include fields needed to complete an order that are not clearly present.

JSON shape:
{
  "customer_name": null,
  "phone_number": null,
  "address": null,
  "order_intent": false,
  "product_name": null,
  "quantity": null,
  "combo": null,
  "confidence": 0.0,
  "missing_fields": []
}
"""


def save_transcript(call_id: str, speaker: str, text: str) -> None:
    clean_text = text.strip()
    if not clean_text:
        return
    with db_session() as session:
        recording_id = _latest_recording_id(session, call_id)
        session.add(
            CallTranscriptRow(
                recording_id=recording_id,
                call_id=call_id,
                speaker=speaker,
                text=clean_text,
            )
        )


def extract_call_intent_for_call(call_id: str) -> dict | None:
    with db_session() as session:
        recording_id = _latest_recording_id(session, call_id)
        if not recording_id:
            return None
        transcripts = session.scalars(
            select(CallTranscriptRow)
            .where(CallTranscriptRow.recording_id == recording_id)
            .order_by(CallTranscriptRow.created_at.asc(), CallTranscriptRow.id.asc())
        ).all()
        customer_texts = [row.text for row in transcripts if row.speaker == "user"]
        if not customer_texts:
            return None

    extracted = extract_intent_from_texts(customer_texts)
    if not extracted:
        return None
    _save_intent(recording_id, call_id, extracted)
    return extracted


def extract_call_intent_for_recording(recording_id: str) -> dict | None:
    with db_session() as session:
        recording = session.get(CallRecordingRow, recording_id)
        if not recording:
            return None
        transcripts = session.scalars(
            select(CallTranscriptRow)
            .where(CallTranscriptRow.recording_id == recording_id)
            .order_by(CallTranscriptRow.created_at.asc(), CallTranscriptRow.id.asc())
        ).all()
        customer_texts = [row.text for row in transcripts if row.speaker == "user"]
        call_id = recording.call_id
        if not customer_texts:
            return None
    extracted = extract_intent_from_texts(customer_texts)
    if not extracted:
        return None
    _save_intent(recording_id, call_id, extracted)
    return extracted


def extract_intent_from_texts(customer_texts: list[str]) -> dict | None:
    transcript = "\n".join(f"Customer: {text}" for text in customer_texts if text.strip())
    if not transcript:
        return None
    prompt = f"{EXTRACTION_PROMPT}\n\nTranscript:\n{transcript}"
    client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=config.gemini.extraction_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    payload = _parse_json_response(getattr(response, "text", "") or "")
    if payload is None:
        return None
    return _sanitize_extraction(payload, customer_texts)


def _save_intent(recording_id: str, call_id: str, extracted: dict) -> None:
    with db_session() as session:
        recording = session.get(CallRecordingRow, recording_id)
        if recording:
            recording.sales_status = _sales_status(extracted)
        session.merge(
            CallIntentRow(
                recording_id=recording_id,
                call_id=call_id,
                customer_name=extracted.get("customer_name"),
                phone_number=extracted.get("phone_number"),
                address=extracted.get("address"),
                order_intent=bool(extracted.get("order_intent")),
                product_name=extracted.get("product_name"),
                quantity=extracted.get("quantity"),
                combo=extracted.get("combo"),
                confidence=float(extracted.get("confidence") or 0.0),
                missing_fields=json.dumps(extracted.get("missing_fields") or [], ensure_ascii=False),
                raw_json=json.dumps(extracted, ensure_ascii=False),
                updated_at=datetime.utcnow(),
            )
        )


def _sales_status(extracted: dict) -> str:
    if not extracted.get("order_intent"):
        return "no_order"
    has_order_item = bool(extracted.get("quantity") or extracted.get("combo") or extracted.get("product_name"))
    if extracted.get("phone_number") and extracted.get("address") and has_order_item:
        return "order_complete"
    return "order_intent"


def _sanitize_extraction(payload: dict, customer_texts: list[str]) -> dict:
    full_text = "\n".join(customer_texts)
    result = {
        "customer_name": _string_or_none(payload.get("customer_name")),
        "phone_number": _phone_or_none(payload.get("phone_number"), full_text),
        "address": _string_or_none(payload.get("address")),
        "order_intent": bool(payload.get("order_intent")),
        "product_name": _string_or_none(payload.get("product_name")),
        "quantity": _int_or_none(payload.get("quantity")),
        "combo": _string_or_none(payload.get("combo")),
        "confidence": _confidence(payload.get("confidence")),
        "missing_fields": _missing_fields(payload.get("missing_fields")),
    }
    if not result["order_intent"]:
        result["quantity"] = None
        result["combo"] = None
    if result["phone_number"] and result["phone_number"] not in _phones_in_text(full_text):
        result["phone_number"] = None
    return result


def _latest_recording_id(session, call_id: str) -> str | None:
    row = session.scalars(
        select(CallRecordingRow)
        .where(CallRecordingRow.call_id == call_id)
        .order_by(desc(CallRecordingRow.started_at))
        .limit(1)
    ).first()
    return row.id if row else None


def _parse_json_response(text: str) -> dict | None:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log(f"[intent] Failed to parse Gemini extraction JSON: {exc}")
        return None
    return parsed if isinstance(parsed, dict) else None


def _string_or_none(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _int_or_none(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _missing_fields(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _phone_or_none(value, text: str) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = _normalize_phone(value)
    if not candidate:
        return None
    return candidate if candidate in _phones_in_text(text) else None


def _phones_in_text(text: str) -> set[str]:
    candidates = re.findall(r"(?:\+?\d[\d\s().-]{6,}\d)", text)
    return {_normalize_phone(candidate) for candidate in candidates if _normalize_phone(candidate)}


def _normalize_phone(value: str) -> str:
    value = value.strip()
    prefix = "+" if value.startswith("+") else ""
    digits = re.sub(r"\D", "", value)
    return f"{prefix}{digits}" if digits else ""
