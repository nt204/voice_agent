import pytest

from app.config import (
    config,
    gemini_initial_greeting,
    gemini_system_instruction,
    product_knowledge,
)
from app.order_extraction import ORDER_EXTRACTION_PROMPT


def test_live_prompt_uses_workflow_rules_not_bug_examples() -> None:
    prompt = gemini_system_instruction("inbound")

    assert "Momo Kawaii" not in prompt
    assert "အသက် ၂၈" not in prompt
    assert "Order workflow" in prompt
    assert "combo comparison are not order confirmation" in prompt
    assert "Always answer in natural Burmese" in prompt


def test_product_knowledge_uses_current_venus_prices_gifts_and_safety_rules() -> None:
    knowledge = product_knowledge()

    assert "၁ ဘူးစျေးနှုန်း: 1ဗူးကို 1သိန်း2သောင်းကျပ်" in knowledge
    assert "Combo ၂: Venus ၂ ဘူး၊ ၂ဗူးကို ၂သိန်း၁သောင်းကျပ်" in knowledge
    assert (
        "Combo ၃: Venus နို့မှုန့် ၃ ဘူးဝယ်လျှင် Venus နို့မှုန့် ၁ ဘူးနှင့် "
        "Venus effervescent tablets ၁ ဘူး လက်ဆောင်ပါဝင်သည်၊ "
        "၃ဗူးကို ၃သိန်း၉သောင်းကျပ်"
    ) in knowledge
    assert (
        "Combo ၅: Venus နို့မှုန့်  ၅ဘူးဝယ်လျှင် Venus နို့မှုန့်  ၂ဘူးနှင့် "
        "Venus effervescent tablets ၂ ဘူး လက်ဆောင်ပါဝင်သည်၊ "
        "၅ဗူးကို ၆သိန်း၃သောင်းကျပ်"
    ) in knowledge
    assert "၂ ဘူးနှင့်အထက် ဝယ်ယူသော အော်ဒါများအတွက် ပို့ခအခမဲ့" in knowledge
    assert "၁ ဘူးတည်းလည်း ဝယ်ယူနိုင်သည်။ ၁ ဘူးမရောင်းဟု မပြောပါနှင့်" in knowledge
    assert "ဆီးချိုရှိသူများ မသုံးသင့်ပါ" in knowledge
    assert "100% အာမခံရလဒ်၊ ကုသပေးနိုင်သည်ဟု မပြောပါနှင့်" in knowledge


def test_live_prompt_has_dedicated_order_confirmation_template() -> None:
    prompt = gemini_system_instruction("inbound")

    assert "Order confirmation template" in prompt
    assert "Recipient name is optional" in prompt
    assert "recipient name when available" in prompt
    assert "{product_name}" in prompt
    assert "{quantity}" in prompt
    assert "{customer_name}" in prompt
    assert "{shipping_address}" in prompt
    assert "Never repeat phone digits in the final order summary" in prompt
    assert "ဖုန်းနံပါတ် အတည်ပြုပြီး" in prompt
    assert "Do not repeat or recalculate the total price" in prompt
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


def test_live_prompt_guides_customer_to_read_phone_digits_in_burmese() -> None:
    prompt = gemini_system_instruction("inbound")

    assert "Phone number listening guide" in prompt
    assert "တစ်လုံးချင်း ဖြည်းဖြည်း" in prompt
    assert "0 = သုည or ဝ" in prompt
    assert "9 = ကိုး" in prompt
    assert "Never speak phone digits" in prompt
    assert "fixed digit-by-digit readback" in prompt


def test_runtime_configuration_prioritizes_myanmar() -> None:
    priorities = [
        item.strip()
        for item in config.gemini.secondary_asr_language_priority.split(",")
    ]

    assert config.gemini.language_code == "my-MM"
    assert priorities[0] == "Burmese"
    assert "Burmese" in config.gemini.system_instruction


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
