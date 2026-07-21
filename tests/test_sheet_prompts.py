from app.sheet_prompts import build_outbound_sheet_prompt


def test_build_outbound_sheet_prompt():
    lead = {
        "name": "Thaw Zin",
        "phone": "+95999999999",
        "product": "Venus BigOne",
        "quantity": "2",
        "address": "Mandalay",
        "notes": "Call before arrival",
    }
    product = {"name": "Venus BigOne"}
    prompt = build_outbound_sheet_prompt(lead, product)
    
    assert "Thaw Zin" in prompt
    assert "Venus BigOne" in prompt
    assert "+95999999999" in prompt
    assert "Mandalay" in prompt
    assert "Call before arrival" in prompt
    assert "Role and Call Objective:" in prompt
