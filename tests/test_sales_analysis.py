from app.sales_analysis import analyze_call


def _customer_turn(text: str) -> dict[str, str]:
    return {"speaker": "customer", "text": text}


def _agent_turn(text: str) -> dict[str, str]:
    return {"speaker": "agent", "text": text}


def test_generic_buy_intent_plus_combo_question_does_not_create_order() -> None:
    transcript = [
        _customer_turn("Tôi muốn mua một combo"),
        _customer_turn("Combo 2 thì thế nào?"),
        _customer_turn("ship đến Mỹ Đình"),
        _customer_turn("Okay စစ်ချောင်းသနပ်"),
    ]

    result = analyze_call(transcript, fallback_phone="+84961984204")

    assert result["analysis"]["intent_status"] == "needs_consultation"
    assert result["customer"]["address"] == "Mỹ Đình"
    assert result["order"] is None


def test_explicit_combo_selection_uses_one_catalog_entry() -> None:
    transcript = [_customer_turn("Tôi muốn mua Combo 2")]

    result = analyze_call(transcript, fallback_phone="+84961984204")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["quantity"] == 2
    assert result["order"]["unit_price"] == 105000
    assert result["order"]["total_price"] == 210000


def test_combo_number_is_not_merged_into_customer_phone() -> None:
    transcript = [
        _customer_turn("Tôi mua combo 2 0961984204"),
        _customer_turn("Địa chỉ là Hà Nội"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["phone"] == "0961984204"
    assert result["order"]["customer_phone"] == "0961984204"
    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["quantity"] == 2


def test_two_boxes_defaults_to_combo_two_unless_customer_says_retail() -> None:
    transcript = [
        _customer_turn("Tôi muốn mua hai hộp"),
        _customer_turn("Tên người nhận là Trần Tuấn Anh"),
        _customer_turn("0961695448"),
        _customer_turn("Địa chỉ là số 2 ngõ 49 Lê Đức Thọ Hà Nội"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["combo"] == "Venus BigOne Combo 2"
    assert result["order"]["quantity"] == 2
    assert result["order"]["total_price"] == 210000


def test_contextual_name_and_address_answers_are_extracted() -> None:
    transcript = [
        _customer_turn("Tôi muốn mua hai hộp"),
        _agent_turn("Anh/chị tên gì ạ?"),
        _customer_turn("Trần Tuấn Anh."),
        _agent_turn("Anh Tuấn cho em xin số điện thoại với ạ."),
        _customer_turn("0961695448."),
        _agent_turn("Anh Tuấn cho em xin địa chỉ giao hàng ạ."),
        _customer_turn("Số 2 ngõ 49 Lê Đức Thọ Hà Nội."),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["name"] == "Trần Tuấn Anh"
    assert result["customer"]["address"] == "Số 2 ngõ 49 Lê Đức Thọ Hà Nội"
    assert result["order"]["customer_name"] == "Trần Tuấn Anh"
    assert result["order"]["shipping_address"] == "Số 2 ngõ 49 Lê Đức Thọ Hà Nội"
    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["total_price"] == 210000
    assert result["order"]["missing_fields"] == []


def test_confirmation_after_readback_does_not_replace_customer_name() -> None:
    transcript = [
        _customer_turn("Tôi muốn mua hai hộp"),
        _agent_turn("Anh/chị tên gì ạ?"),
        _customer_turn("Trần Tuấn Anh."),
        _agent_turn("Anh Tuấn cho em xin số điện thoại với ạ."),
        _customer_turn("0961695448."),
        _agent_turn("Anh Tuấn cho em xin địa chỉ giao hàng ạ."),
        _customer_turn("Số 2 ngõ 49 Lê Đức Thọ Hà Nội."),
        _agent_turn("Em xác nhận Combo 2, Trần Tuấn Anh, 0961695448, địa chỉ trên đúng không ạ?"),
        _customer_turn("Dạ đúng rồi, lên đơn cho tôi nhé."),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["name"] == "Trần Tuấn Anh"
    assert result["order"]["customer_name"] == "Trần Tuấn Anh"


def test_retail_two_boxes_stays_retail_price() -> None:
    transcript = [
        _customer_turn("Tôi chọn mua lẻ 2 hộp Venus BigOne"),
        _customer_turn("Tên người nhận là Trần Tuấn Anh"),
        _customer_turn("0961695448"),
        _customer_turn("Địa chỉ là số 2 ngõ 49 Lê Đức Thọ Hà Nội"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["order"]["product_name"] == "Venus BigOne"
    assert result["order"]["combo"] == ""
    assert result["order"]["quantity"] == 2
    assert result["order"]["total_price"] == 240000


def test_order_captures_optional_customer_name() -> None:
    transcript = [
        _customer_turn("Tôi mua combo 2"),
        _customer_turn("Tên người nhận là Nguyễn Văn A"),
        _customer_turn("Số điện thoại là 0961984204"),
        _customer_turn("Địa chỉ là Hà Nội"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["name"] == "Nguyễn Văn A"
    assert result["order"]["customer_name"] == "Nguyễn Văn A"
    assert result["order"]["missing_fields"] == []


def test_incomplete_name_turn_is_not_saved_as_customer_name() -> None:
    transcript = [
        _customer_turn("Tôi muốn mua một"),
        _customer_turn("Tên là"),
        _customer_turn("0961695448"),
        _customer_turn("Địa chỉ là số 2 ngõ 49 đường Lê Đức Thọ Hà Nội"),
    ]

    result = analyze_call(transcript, fallback_phone="")

    assert result["customer"]["name"] == ""
    assert result["order"]["customer_name"] == ""
    assert result["order"]["customer_phone"] == "0961695448"


def test_generic_intent_followed_by_plain_selection_is_an_order() -> None:
    transcript = [
        _customer_turn("Tôi muốn mua một combo"),
        _customer_turn("Combo 2"),
    ]

    result = analyze_call(transcript, fallback_phone="+84961984204")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["order"]["quantity"] == 2


def test_incomplete_spoken_phone_does_not_use_metadata_phone() -> None:
    transcript = [
        _customer_turn("Venus BigOne 2 hộp tôi mua"),
        _customer_turn("số điện thoại không chín sáu một"),
    ]

    result = analyze_call(transcript, fallback_phone="+84961984204")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["phone"] == ""
    assert "customer_phone" in result["order"]["missing_fields"]


def test_final_batch_transcript_uses_delivery_place_and_latest_combo() -> None:
    transcript = [
        _customer_turn("Tôi muốn mua một combo."),
        _customer_turn("Combo 2 thì thế nào?"),
        _customer_turn("Ship cho tôi một combo 3."),
        _customer_turn("Combo 3."),
        _customer_turn("Ship đến Mỹ Đình."),
        _customer_turn("Ok, ship cho Tuấn Anh."),
    ]

    result = analyze_call(transcript, fallback_phone="+84961984204")

    assert result["analysis"]["intent_status"] == "ready_to_order"
    assert result["customer"]["address"] == "Mỹ Đình"
    assert result["order"]["product_name"] == "Venus BigOne Combo 3"
    assert result["order"]["quantity"] == 3
    assert result["order"]["total_price"] == 390000
