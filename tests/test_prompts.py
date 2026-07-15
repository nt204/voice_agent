import pytest

from app.config import gemini_initial_greeting, gemini_system_instruction
from app.order_extraction import ORDER_EXTRACTION_PROMPT


def test_live_prompt_uses_workflow_rules_not_bug_examples() -> None:
    prompt = gemini_system_instruction("inbound")

    assert "Momo Kawaii" not in prompt
    assert "အသက် ၂၈" not in prompt
    assert "Quy trình đặt hàng" in prompt
    assert "so sánh combo không phải là xác nhận đặt hàng" in prompt
    assert "မြန်မာဘာသာဖြင့်" not in prompt


def test_live_prompt_has_dedicated_order_confirmation_template() -> None:
    prompt = gemini_system_instruction("inbound")

    assert "Template xác nhận thông tin đơn hàng" in prompt
    assert "Tên người nhận nên có nếu khách cung cấp" in prompt
    assert "tên người nhận nếu có" in prompt
    assert "{product_name}" in prompt
    assert "{quantity}" in prompt
    assert "{customer_name}" in prompt
    assert "{customer_phone}" in prompt
    assert "{shipping_address}" in prompt
    assert "Nếu khách sửa thông tin" in prompt


def test_live_prompt_handles_acknowledgement_price_and_name_collection_rules() -> None:
    prompt = gemini_system_instruction("outbound")

    assert 'khách chỉ nói "dạ"' in prompt
    assert "không được tự hiểu là khách bận" in prompt
    assert "Quy tắc tư vấn giá và combo" in prompt
    assert "không hỏi chốt đơn ngay" in prompt
    assert "chỉ trả lời giá của combo đó" in prompt
    assert "hỏi tên người nhận trước" in prompt


def test_initial_greetings_are_mode_specific() -> None:
    inbound = gemini_initial_greeting("inbound")
    outbound = gemini_initial_greeting("outbound")

    assert inbound != outbound
    assert "cần tư vấn" in inbound
    assert "tiện trao đổi" in outbound


def test_initial_greeting_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        gemini_initial_greeting("sideways")


def test_order_prompt_is_concise_and_requires_concrete_selection() -> None:
    assert "Examples that must" not in ORDER_EXTRACTION_PROMPT
    assert "age 28" not in ORDER_EXTRACTION_PROMPT
    assert "identifiable product or variant" in ORDER_EXTRACTION_PROMPT
    assert "questions about a\n  combo are not enough" in ORDER_EXTRACTION_PROMPT
    assert len(ORDER_EXTRACTION_PROMPT.splitlines()) < 35
