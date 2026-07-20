from app.sales_analysis import analyze_call


def _customer_turn(text: str) -> dict[str, str]:
    return {"speaker": "customer", "text": text}


def _agent_turn(text: str) -> dict[str, str]:
    return {"speaker": "agent", "text": text}


def test_generic_buy_intent_plus_combo_question_does_not_create_order() -> None:
    transcript = [
        _customer_turn("ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်"),
        _customer_turn("Combo 2 က ဘယ်လိုလဲ"),
        _customer_turn("ship to Yangon Hlaing"),
    ]

    result = analyze_call(transcript, fallback_phone="+95961984204")

    assert result["analysis"]["intent_status"] == "needs_consultation"
    assert result["customer"]["address"] == "Yangon Hlaing"
    assert result["order"] is None


def test_explicit_combo_selection_uses_one_catalog_entry() -> None:
    transcript = [_customer_turn("ကွန်ဘို ၂ မှာယူမယ်")]

    result = analyze_call(transcript, fallback_phone="+95961984204")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["quantity"] == 2
    assert result["order"]["unit_price"] == 105000
    assert result["order"]["total_price"] == 210000


def test_combo_number_is_not_merged_into_customer_phone() -> None:
    transcript = [
        _customer_turn("ကွန်ဘို ၂ မှာယူမယ် ဖုန်း 0961984204"),
        _customer_turn("လိပ်စာက Yangon Hlaing"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["phone"] == "0961984204"
    assert result["order"]["customer_phone"] == "0961984204"
    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["quantity"] == 2


def test_spoken_burmese_phone_words_are_extracted() -> None:
    transcript = [
        _customer_turn("ကွန်ဘို ၂ မှာယူမယ်"),
        _customer_turn(
            "ဖုန်း သုည ကိုးခြောက် တစ်ခြောက် ကိုး ငါးလေးလေးရှစ် "
            "လိပ်စာက Yangon Hlaing"
        ),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["phone"] == "0961695448"
    assert result["order"]["customer_phone"] == "0961695448"
    assert result["order"]["missing_fields"] == []


def test_two_boxes_defaults_to_combo_two_unless_customer_says_retail() -> None:
    transcript = [
        _customer_turn("Venus BigOne ၂ ဘူး ဝယ်မယ်"),
        _customer_turn("နာမည်က Aung Min"),
        _customer_turn("ဖုန်း 0961695448"),
        _customer_turn("လိပ်စာက No. 2 Insein Road, Yangon"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["combo"] == "Venus BigOne Combo 2"
    assert result["order"]["quantity"] == 2
    assert result["order"]["total_price"] == 210000


def test_contextual_name_and_address_answers_are_extracted() -> None:
    transcript = [
        _customer_turn("Venus BigOne ၂ ဘူး ဝယ်မယ်"),
        _agent_turn("လက်ခံမယ့်နာမည်လေး ပြောပေးပါရှင်။"),
        _customer_turn("Aung Min."),
        _agent_turn("ဖုန်းနံပါတ်လေး ပြောပေးပါရှင်။"),
        _customer_turn("0961695448."),
        _agent_turn("ပို့ရန်လိပ်စာလေး ပြောပေးပါရှင်။"),
        _customer_turn("No. 2 Insein Road, Yangon."),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["name"] == "Aung Min"
    assert result["customer"]["address"] == "No. 2 Insein Road, Yangon"
    assert result["order"]["customer_name"] == "Aung Min"
    assert result["order"]["shipping_address"] == "No. 2 Insein Road, Yangon"
    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["total_price"] == 210000
    assert result["order"]["missing_fields"] == []


def test_agent_address_readback_can_restore_full_delivery_address() -> None:
    transcript = [
        _customer_turn("Venus BigOne ၂ ဘူး ဝယ်မယ်"),
        _customer_turn("ဖုန်း သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ် တစ် လေး သုံး သုံး"),
        _agent_turn("ပို့ရမယ့်လိပ်စာလေး ပြောပေးပါရှင်။"),
        _customer_turn("အမှတ် ၄၈ သာကေတမြို့နယ်ပါ"),
        _agent_turn("ပို့ရမယ့်လိပ်စာက အမှတ် (၄၈)၊ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်၊ ရန်ကုန် ဟုတ်ပါသလားရှင်။"),
        _customer_turn("၁၈ မဟုတ်ဘူးနော် အမှတ် ၄၈ ပါ"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["address"] == "အမှတ် (၄၈)၊ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်၊ ရန်ကုန်"
    assert result["order"]["shipping_address"] == "အမှတ် (၄၈)၊ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်၊ ရန်ကုန်"


def test_confirmation_after_readback_does_not_replace_customer_name() -> None:
    transcript = [
        _customer_turn("Venus BigOne ၂ ဘူး ဝယ်မယ်"),
        _agent_turn("လက်ခံမယ့်နာမည်လေး ပြောပေးပါရှင်။"),
        _customer_turn("Aung Min."),
        _agent_turn("ဖုန်းနံပါတ်လေး ပြောပေးပါရှင်။"),
        _customer_turn("0961695448."),
        _agent_turn("ပို့ရန်လိပ်စာလေး ပြောပေးပါရှင်။"),
        _customer_turn("No. 2 Insein Road, Yangon."),
        _agent_turn("Combo 2၊ Aung Min၊ 0961695448၊ No. 2 Insein Road, Yangon မှန်ပါသလားရှင်။"),
        _customer_turn("ဟုတ်ကဲ့ မှန်ပါတယ်၊ အော်ဒါတင်ပေးပါရှင်။"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["name"] == "Aung Min"
    assert result["order"]["customer_name"] == "Aung Min"


def test_retail_two_boxes_stays_retail_price() -> None:
    transcript = [
        _customer_turn("လက်လီ ၂ ဘူး Venus BigOne ဝယ်မယ်"),
        _customer_turn("နာမည်က Aung Min"),
        _customer_turn("ဖုန်း 0961695448"),
        _customer_turn("လိပ်စာက No. 2 Insein Road, Yangon"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["order"]["product_name"] == "Venus BigOne"
    assert result["order"]["combo"] == ""
    assert result["order"]["quantity"] == 2
    assert result["order"]["total_price"] == 240000


def test_order_captures_optional_customer_name() -> None:
    transcript = [
        _customer_turn("ကွန်ဘို ၂ မှာယူမယ်"),
        _customer_turn("နာမည်က Aung Min"),
        _customer_turn("ဖုန်း 0961984204"),
        _customer_turn("လိပ်စာက Yangon Hlaing"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["name"] == "Aung Min"
    assert result["order"]["customer_name"] == "Aung Min"
    assert result["order"]["missing_fields"] == []


def test_incomplete_name_turn_is_not_saved_as_customer_name() -> None:
    transcript = [
        _customer_turn("Venus BigOne တစ်ဘူး ဝယ်မယ်"),
        _customer_turn("နာမည်က"),
        _customer_turn("ဖုန်း 0961695448"),
        _customer_turn("လိပ်စာက No. 2 Insein Road, Yangon"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["name"] == ""
    assert result["order"]["customer_name"] == ""
    assert result["order"]["customer_phone"] == "0961695448"


def test_generic_intent_followed_by_plain_selection_is_an_order() -> None:
    transcript = [
        _customer_turn("ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်"),
        _customer_turn("Combo 2"),
    ]

    result = analyze_call(transcript, fallback_phone="+95961984204")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["order"]["quantity"] == 2


def test_incomplete_spoken_phone_does_not_use_metadata_phone() -> None:
    transcript = [
        _customer_turn("Venus BigOne ၂ ဘူး ဝယ်မယ်"),
        _customer_turn("ဖုန်း သုည ကိုးခြောက် တစ်"),
    ]

    result = analyze_call(transcript, fallback_phone="+95961984204")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["phone"] == ""
    assert "customer_phone" in result["order"]["missing_fields"]


def test_non_myanmar_metadata_phone_is_ignored() -> None:
    transcript = [_customer_turn("ကွန်ဘို ၂ မှာယူမယ်")]

    result = analyze_call(transcript, fallback_phone="+12025550123")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["phone"] == ""
    assert "customer_phone" in result["order"]["missing_fields"]


def test_clearly_non_myanmar_shipping_address_is_rejected() -> None:
    transcript = [
        _customer_turn("ကွန်ဘို ၂ မှာယူမယ်"),
        _customer_turn("ဖုန်း 0961695448"),
        _customer_turn("လိပ်စာက No. 12 Nguyen Trai Street, Hanoi, Vietnam"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["address"] == ""
    assert result["order"]["shipping_address"] == ""
    assert "shipping_address" in result["order"]["missing_fields"]


def test_final_batch_transcript_uses_delivery_place_and_latest_combo() -> None:
    transcript = [
        _customer_turn("ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။"),
        _customer_turn("Combo 2 က ဘယ်လိုလဲ"),
        _customer_turn("Ship one combo 3."),
        _customer_turn("Combo 3."),
        _customer_turn("လိပ်စာက Yangon Hlaing."),
    ]

    result = analyze_call(transcript, fallback_phone="+95961984204")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["address"] == "Yangon Hlaing"
    assert result["order"]["product_name"] == "Venus BigOne Combo 3"
    assert result["order"]["quantity"] == 3
    assert result["order"]["total_price"] == 390000


def test_common_audio_asr_confusion_still_creates_combo_two_order() -> None:
    transcript = [
        _customer_turn("ပြန်နှိပ်ဖူးပြီနော် အော်ဒါတင်ပေးပါနော်"),
        _customer_turn("သုည ကိုး"),
        _customer_turn("သုည ကိုး ၇၈ သုည ၇၇ ၁ ၄၉၄ ပါ"),
        _customer_turn("သုည ကိုး ၇၇"),
        _customer_turn(
            "သုည ကိုး ၇၈ သုည ပါနော် ၈၈ သုည မဟုတ်ဘူးနော် သုည ကိုး ၇၈ သုည ၇၇ ၁ ၄၉၄ ပါ"
        ),
        _agent_turn("ပို့ရမယ့် လိပ်စာလေး ပြောပေးပါရှင်။"),
        _customer_turn("လိပ်စာပို့ လိပ်စာပြောပေးမယ်နော်"),
        _customer_turn("အမှတ် ၂၈ မဟုတ်ဘူးနော် အမှတ် ၄၈ ပါ"),
        _agent_turn("လမ်းနာမည်နဲ့ မြို့နယ်လေး ပါ ပြောပေးပါဦးရှင်။"),
        _customer_turn("အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ် ၂ ရပ်ကွက်ပါ"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["quantity"] == 2
    assert result["customer"]["phone"] == "09780771494"
    assert result["customer"]["address"] == "အမှတ် ၄၈ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ် ၂ ရပ်ကွက်"
    assert result["customer"]["name"] == ""
    assert result["order"]["status"] == "ready_to_confirm"
    assert result["order"]["missing_fields"] == []


def test_corrected_phone_with_only_partial_latest_attempt_stays_missing() -> None:
    transcript = [
        _customer_turn("နှစ်ဘူးယူမယ် အော်ဒါတင်ပေးပါနော်"),
        _customer_turn(
            "သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ် တစ် လေး သုံး သုံး "
            "သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ် တစ် လေး သုံး သုံးပါ "
            "အာ မဟုတ်ဘူးနော် ဖုန်းနံပါတ်မှားနေတယ်နော် ပြန်ပြောပေးမယ်နော် "
            "သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ်"
        ),
        _customer_turn("လိပ်စာက အမှတ် ၄၈ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ်"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["phone"] == ""
    assert result["order"]["status"] == "missing_info"
    assert "customer_phone" in result["order"]["missing_fields"]


def test_phone_rejected_after_latest_full_candidate_stays_missing() -> None:
    transcript = [
        _customer_turn("Venus BigOne နှစ်ဘူး ယူမယ်"),
        _customer_turn("သုည ကိုး ကိုး ကိုး သုံး ကိုး သုည ငါး တစ် ငါး သုံး ပါ"),
        _agent_turn("ဖုန်းနံပါတ် ၀ ၉ ၉ ၉ ၃ ၉ ၀ ၅ ၁ ၅ ၃ မှန်ပါသလားရှင်။"),
        _customer_turn("အော် ရီရတယ်နော် အကုန်လုံး မှားနေတယ်"),
        _customer_turn("လိပ်စာက အမှတ် ၄၈ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ်"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["phone"] == ""
    assert result["order"]["customer_phone"] == ""
    assert result["order"]["status"] == "missing_info"
    assert "customer_phone" in result["order"]["missing_fields"]


def test_phone_readback_without_clear_confirmation_stays_missing() -> None:
    transcript = [
        _customer_turn("Venus BigOne နှစ်ဘူး ယူမယ်"),
        _customer_turn("ဖုန်း 0961695448 ပါ"),
        _agent_turn("ဖုန်းနံပါတ် ၀ ۹ ۶ ۱ ۶ ۹ ۵ ۴ ۴ ۸ မှန်ပါသလားရှင်။"),
        _customer_turn("လိပ်စာက အမှတ် ၄۸ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ်"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["phone"] == ""
    assert result["order"]["customer_phone"] == ""
    assert result["order"]["status"] == "missing_info"
    assert "customer_phone" in result["order"]["missing_fields"]


def test_final_all_details_confirmation_keeps_confirmed_phone() -> None:
    transcript = [
        _customer_turn("ကွန်ဂိုသုံးကို မှာယူမယ်"),
        _agent_turn("ဖုန်းနံပါတ် 09780771433 မှန်ပါသလားရှင်။"),
        _customer_turn("ဟုတ်ကဲ့ ဖုန်းနံပါတ် 0970771433 က မှန်ပါတယ်ရှင်"),
        _customer_turn("ဖုန်းနံပါတ် 09780771433 မှန်ပါတယ်"),
        _customer_turn("လိပ်စာက No. 123 Bogyoke Road, Yangon ပါ"),
        _customer_turn("ဖုန်းနံပါတ်နဲ့ လိပ်စာ အားလုံးမှန်ပါတယ်"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["phone"] == "09780771433"
    assert result["order"]["customer_phone"] == "09780771433"
    assert result["order"]["status"] == "ready_to_confirm"
