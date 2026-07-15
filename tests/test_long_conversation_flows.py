from app.sales_analysis import analyze_call


def turn(speaker: str, text: str) -> dict[str, str]:
    return {"speaker": speaker, "text": text}


def test_long_vietnamese_inbound_retail_order_with_confirmed_caller_phone() -> None:
    transcript = [
        turn("agent", "Xin chào, đây là Venus BigOne. Anh/chị cần tư vấn nội dung nào ạ?"),
        turn("customer", "Tôi thấy quảng cáo nhưng chưa hiểu sản phẩm này dùng để làm gì."),
        turn("agent", "Sản phẩm hỗ trợ chăm sóc sắc đẹp và vóc dáng cho phụ nữ ạ."),
        turn("customer", "Tôi đang cho con bú thì có dùng luôn được không?"),
        turn("agent", "Chị nên hỏi bác sĩ hoặc dược sĩ trước khi dùng trong thời gian cho con bú ạ."),
        turn("customer", "Thế một hộp bao nhiêu, dùng được mấy ngày?"),
        turn("agent", "Một hộp 120.000 kyat và dùng khoảng 15 ngày ạ."),
        turn("customer", "Combo 2 với Combo 3 khác nhau thế nào, có quà không?"),
        turn("agent", "Combo 2 gồm 2 hộp giá 210.000 kyat; Combo 3 giá 390.000 kyat và có quà theo thông tin sản phẩm ạ."),
        turn("customer", "Tôi chọn mua lẻ 2 hộp Venus BigOne."),
        turn("agent", "Anh cho em xin tên người nhận hàng ạ?"),
        turn("customer", "Tên người nhận là Nguyễn Tuấn Anh."),
        turn("agent", "Số điện thoại nhận hàng 0 9 6 1 9 8 4 2 0 4 có đúng không ạ?"),
        turn("customer", "Vâng, đúng số đó rồi."),
        turn("agent", "Anh cho em xin địa chỉ nhận hàng ạ?"),
        turn("customer", "Địa chỉ là số 18 ngõ 72 đường Mỹ Đình, Nam Từ Liêm, Hà Nội."),
        turn("agent", "Em xác nhận 2 hộp mua lẻ, người nhận Nguyễn Tuấn Anh, số 0961984204, địa chỉ số 18 ngõ 72 đường Mỹ Đình, Nam Từ Liêm, Hà Nội, đúng không ạ?"),
        turn("customer", "Đúng hết rồi, xác nhận đơn giúp tôi."),
    ]

    result = analyze_call(transcript, fallback_phone="+84961984204")

    assert result["customer"]["need"] == "Mua lẻ 2 hộp Venus BigOne"
    assert result["order"] == {
        "customer_phone": "+84961984204",
        "customer_name": "Nguyễn Tuấn Anh",
        "shipping_address": "số 18 ngõ 72 đường Mỹ Đình, Nam Từ Liêm, Hà Nội",
        "product_name": "Venus BigOne",
        "purchase_type": "retail",
        "combo": "",
        "quantity": 2,
        "unit_price": 120000,
        "total_price": 240000,
        "status": "ready_to_confirm",
        "missing_fields": [],
        "confidence": 0.9,
    }


def test_long_myanmar_combo_order_replaces_caller_phone() -> None:
    transcript = [
        turn("agent", "မင်္ဂလာပါရှင်။ Venus BigOne ကပါ။ ဘာအကြောင်း အကြံပြုပေးရမလဲရှင်။"),
        turn("customer", "ဒီနို့မှုန့်က ဘာအတွက်လဲ၊ ဆီးချိုရှိရင် သောက်လို့ရလားရှင်။"),
        turn("agent", "အလှအပနဲ့ ခန္ဓာကိုယ်ထိန်းသိမ်းမှုကို အထောက်အကူပြုတာပါရှင်။ ဆီးချိုရှိသူ မသုံးသင့်ပါဘူးရှင်။"),
        turn("customer", "ကွန်ဘို ၃ နဲ့ ကွန်ဘို ၅ စျေးနဲ့ လက်ဆောင် ဘာကွာလဲ။"),
        turn("agent", "ကွန်ဘို ၃ က ၃၉၀၀၀၀ ကျပ်၊ ကွန်ဘို ၅ က ၆၃၀၀၀၀ ကျပ်ဖြစ်ပြီး လက်ဆောင်အရေအတွက် ကွာပါတယ်ရှင်။"),
        turn("customer", "အရင်ဆုံး ကွန်ဘို ၃ ကို မှာယူမယ်ရှင်။"),
        turn("agent", "ပစ္စည်းလက်ခံမယ့် နာမည်လေး ပြောပေးပါရှင်။"),
        turn("customer", "နာမည်က May Thinzar ပါရှင်။"),
        turn("agent", "ပို့ဆောင်ရန် ဖုန်းနံပါတ် ၀ ၉ ၇ ၇ ၁ ၂ ၃ ၄ ၅ ၆ ၇ က မှန်ပါသလားရှင်။"),
        turn("customer", "မဟုတ်ပါဘူးရှင်၊ ပို့ရမယ့် ဖုန်းနံပါတ်က ၀၉၆၁၆၉၅၄၄၈ ပါ။"),
        turn("agent", "ဖုန်းနံပါတ် ၀ ၉ ၆ ၁ ၆ ၉ ၅ ၄ ၄ ၈ က မှန်ပါသလားရှင်။"),
        turn("customer", "ဟုတ်ကဲ့ မှန်ပါတယ်ရှင်။"),
        turn("agent", "ပို့ဆောင်ရမယ့် လိပ်စာလေး ပြောပေးပါရှင်။"),
        turn("customer", "လိပ်စာက အမှတ် ၁၂၃၊ ဗိုလ်ချုပ်လမ်း၊ လသာမြို့နယ်၊ ရန်ကုန် ပါရှင်။"),
        turn("agent", "ကွန်ဘို ၃၊ May Thinzar၊ ၀၉၆၁၆၉၅၄၄၈၊ အမှတ် ၁၂၃ ဗိုလ်ချုပ်လမ်း လသာမြို့နယ် ရန်ကုန်ဆို မှန်ပါသလားရှင်။"),
        turn("customer", "ဟုတ်ကဲ့ အားလုံးမှန်ပါတယ်ရှင်။"),
    ]

    result = analyze_call(transcript, fallback_phone="+959771234567")

    assert result["customer"]["need"] == "Mua Combo 3"
    assert result["order"]["product_name"] == "Venus BigOne Combo 3"
    assert result["order"]["purchase_type"] == "combo"
    assert result["order"]["quantity"] == 3
    assert result["order"]["customer_name"] == "May Thinzar"
    assert result["order"]["customer_phone"] == "0961695448"
    assert result["order"]["shipping_address"] == "အမှတ် ၁၂၃၊ ဗိုလ်ချုပ်လမ်း၊ လသာမြို့နယ်၊ ရန်ကုန်"
    assert result["order"]["total_price"] == 390000
    assert result["order"]["missing_fields"] == []
    assert result["order"]["status"] == "ready_to_confirm"


def test_long_order_uses_latest_product_name_phone_and_address_corrections() -> None:
    transcript = [
        turn("customer", "Cho tôi hỏi Combo 2 và Combo 3 có những gì?"),
        turn("agent", "Combo 2 gồm 2 hộp; Combo 3 gồm 3 hộp và có quà theo thông tin sản phẩm ạ."),
        turn("customer", "Tôi chốt mua Combo 2."),
        turn("customer", "Tôi đổi lại, chốt mua Combo 3 nhé."),
        turn("agent", "Tên người nhận hàng là gì ạ?"),
        turn("customer", "Tên tôi là Trần Minh."),
        turn("customer", "Sửa tên người nhận là Trần Minh Ngọc."),
        turn("agent", "Số điện thoại nhận hàng 0 9 0 1 1 1 2 2 3 3 có đúng không ạ?"),
        turn("customer", "Không, số điện thoại nhận hàng là 0987654321."),
        turn("agent", "Số 0 9 8 7 6 5 4 3 2 1 đúng không ạ?"),
        turn("customer", "Đúng rồi."),
        turn("customer", "Địa chỉ là số 7 đường Láng, Hà Nội."),
        turn("customer", "Tôi muốn sửa lại địa chỉ nhận hàng."),
        turn("agent", "Địa chỉ mới là gì ạ?"),
        turn("customer", "Địa chỉ là căn 1208, tòa S2, Vinhomes Ocean Park, Gia Lâm, Hà Nội."),
        turn("agent", "Em đọc lại toàn bộ đơn, chị xác nhận giúp em nhé."),
        turn("customer", "Đúng rồi, xác nhận theo thông tin mới nhất."),
    ]

    result = analyze_call(transcript, fallback_phone="+84901112233")

    assert result["order"]["product_name"] == "Venus BigOne Combo 3"
    assert result["order"]["customer_name"] == "Trần Minh Ngọc"
    assert result["order"]["customer_phone"] == "0987654321"
    assert result["order"]["shipping_address"] == "căn 1208, tòa S2, Vinhomes Ocean Park, Gia Lâm, Hà Nội"
    assert result["order"]["missing_fields"] == []


def test_long_completed_details_are_not_an_order_after_customer_cancels() -> None:
    transcript = [
        turn("customer", "Tôi mua Combo 2."),
        turn("customer", "Tên người nhận là Lê Mai Anh."),
        turn("customer", "Số điện thoại là 0912345678."),
        turn("customer", "Địa chỉ là 25 Trần Duy Hưng, Cầu Giấy, Hà Nội."),
        turn("agent", "Em xin xác nhận lại đơn Combo 2 với các thông tin trên ạ."),
        turn("customer", "Khoan, tôi không mua nữa, hủy đơn giúp tôi."),
    ]

    result = analyze_call(transcript, fallback_phone="+84900000000")

    assert result["analysis"]["intent_status"] == "no_need"
    assert result["customer"]["need"] == "Chưa có nhu cầu"
    assert result["order"] is None


def test_long_price_comparison_never_becomes_an_order_without_selection() -> None:
    transcript = [
        turn("customer", "Một hộp giá bao nhiêu?"),
        turn("agent", "Một hộp giá 120.000 kyat ạ."),
        turn("customer", "Nếu 2 hộp thì bao nhiêu, 3 hộp thì có quà gì?"),
        turn("agent", "Combo 2 giá 210.000 kyat; Combo 3 giá 390.000 kyat và có quà ạ."),
        turn("customer", "Combo 5 có miễn phí giao hàng không?"),
        turn("agent", "Đơn từ 2 hộp trở lên được miễn phí giao hàng ạ."),
        turn("customer", "Tôi chỉ đang hỏi để cân nhắc, chưa chốt mua."),
    ]

    result = analyze_call(transcript, fallback_phone="+84961984204")

    assert result["analysis"]["intent_status"] == "considering"
    assert result["order"] is None


def test_outbound_rejection_never_creates_an_order() -> None:
    transcript = [
        turn("agent", "Xin chào, em gọi từ Venus BigOne. Hiện tại anh/chị có tiện trao đổi ngắn không ạ?"),
        turn("customer", "Không, tôi không quan tâm và đừng gọi lại số này nữa."),
        turn("agent", "Em đã ghi nhận, xin lỗi đã làm phiền anh/chị."),
    ]

    result = analyze_call(transcript, fallback_phone="+84961984204")

    assert result["analysis"]["intent_status"] == "no_need"
    assert result["order"] is None
