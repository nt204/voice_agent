import pytest

from app.config import gemini_initial_greeting, gemini_system_instruction
from app.order_extraction import ORDER_EXTRACTION_PROMPT


def test_live_prompt_uses_workflow_rules_not_bug_examples() -> None:
    prompt = gemini_system_instruction("inbound")

    assert "Momo Kawaii" not in prompt
    assert "အသက် ၂၈" not in prompt
    assert "Order workflow" in prompt
    assert "combo comparison are not order confirmation" in prompt
    assert "Always answer in natural Burmese" in prompt


def test_live_prompt_has_dedicated_order_confirmation_template() -> None:
    prompt = gemini_system_instruction("inbound")

    assert "Order confirmation template" in prompt
    assert "Recipient name is optional" in prompt
    assert "recipient name when available" in prompt
    assert "{product_name}" in prompt
    assert "{quantity}" in prompt
    assert "{customer_name}" in prompt
    assert "{customer_phone}" in prompt
    assert "{shipping_address}" in prompt
    assert "latest correction" in prompt


def test_live_prompt_handles_acknowledgement_price_and_name_collection_rules() -> None:
    prompt = gemini_system_instruction("outbound")

    assert '"ဟုတ်ကဲ့"' in prompt
    assert "unless they clearly say they are busy" in prompt
    assert "Price and combo consultation rules" in prompt
    assert "do not ask to close the order immediately" in prompt
    assert "answer only that combo's price" in prompt
    assert "ask for recipient name first" in prompt
    assert "Myanmar delivery location" in prompt


def test_initial_greetings_are_mode_specific() -> None:
    inbound = gemini_initial_greeting("inbound")
    outbound = gemini_initial_greeting("outbound")

    assert inbound != outbound
    assert "အကြံပြုပေး" in inbound
    assert "ခဏပြောလို့ရမလား" in outbound


def test_initial_greeting_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        gemini_initial_greeting("sideways")


def test_order_prompt_is_concise_and_requires_concrete_selection() -> None:
    assert "Examples that must" not in ORDER_EXTRACTION_PROMPT
    assert "age 28" not in ORDER_EXTRACTION_PROMPT
    assert "Burmese for the Myanmar market" in ORDER_EXTRACTION_PROMPT
    assert "identifiable product or variant" in ORDER_EXTRACTION_PROMPT
    assert "must be a Myanmar delivery address" in ORDER_EXTRACTION_PROMPT
    assert "questions about a\n  combo are not enough" in ORDER_EXTRACTION_PROMPT
    assert len(ORDER_EXTRACTION_PROMPT.splitlines()) < 40
