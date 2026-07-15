from app.config import gemini_system_instruction
from app.order_extraction import ORDER_EXTRACTION_PROMPT


def test_live_prompt_uses_workflow_rules_not_bug_examples() -> None:
    prompt = gemini_system_instruction("inbound")

    assert "Momo Kawaii" not in prompt
    assert "အသက် ၂၈" not in prompt
    assert "အော်ဒါလုပ်ငန်းစဉ်" in prompt
    assert "combo နှိုင်းယှဉ်ခြင်းသည် အော်ဒါအတည်ပြုခြင်း မဟုတ်ပါ" in prompt


def test_order_prompt_is_concise_and_requires_concrete_selection() -> None:
    assert "Examples that must" not in ORDER_EXTRACTION_PROMPT
    assert "age 28" not in ORDER_EXTRACTION_PROMPT
    assert "identifiable product or variant" in ORDER_EXTRACTION_PROMPT
    assert "questions about a\n  combo are not enough" in ORDER_EXTRACTION_PROMPT
    assert len(ORDER_EXTRACTION_PROMPT.splitlines()) < 35
