from app.sales_analysis import analyze_call


def turn(speaker: str, text: str) -> dict[str, str]:
    return {"speaker": speaker, "text": text}


def test_long_myanmar_inbound_retail_order_with_confirmed_caller_phone() -> None:
    transcript = [
        turn("agent", "မင်္ဂလာပါရှင်။ Venus BigOne ကပါ။ ဘာအကြောင်း အကြံပြုပေးရမလဲရှင်။"),
        turn("customer", "ဒီနို့မှုန့်က ဘာအတွက်လဲ၊ ဆီးချိုရှိရင် သောက်လို့ရလားရှင်။"),
        turn("agent", "အလှအပနဲ့ ခန္ဓာကိုယ်ထိန်းသိမ်းမှုကို အထောက်အကူပြုတာပါရှင်။ ဆီးချိုရှိသူ မသုံးသင့်ပါဘူးရှင်။"),
        turn("customer", "တစ်ဘူးစျေးဘယ်လောက်လဲ၊ ဘယ်နှရက်သောက်လို့ရလဲ။"),
        turn("agent", "တစ်ဘူး ၁၂၀၀၀၀ ကျပ် ဖြစ်ပြီး ၁၅ ရက်ခန့် သောက်လို့ရပါတယ်ရှင်။"),
        turn("customer", "Combo 2 နဲ့ Combo 3 က ဘာကွာလဲ။"),
        turn("agent", "Combo 2 က ၂ ဘူး ၂၁၀၀၀၀ ကျပ်၊ Combo 3 က ၃၉၀၀၀၀ ကျပ်နဲ့ လက်ဆောင်ပါပါတယ်ရှင်။"),
        turn("customer", "လက်လီ ၂ ဘူး Venus BigOne ဝယ်မယ်။"),
        turn("agent", "လက်ခံမယ့်နာမည်လေး ပြောပေးပါရှင်။"),
        turn("customer", "နာမည်က Aung Min ပါ။"),
        turn("agent", "ဖုန်းနံပါတ်က ၀၉၆၁၉၈၄၂၀၄ မှန်ပါသလားရှင်။"),
        turn("customer", "ဟုတ်ကဲ့ မှန်ပါတယ်။"),
        turn("agent", "ပို့ရန်လိပ်စာလေး ပြောပေးပါရှင်။"),
        turn("customer", "လိပ်စာက No. 18 Myaynigone Road, Sanchaung, Yangon ပါရှင်။"),
        turn("agent", "Venus BigOne ၂ ဘူး၊ Aung Min၊ ၀၉၆၁၉၈၄၂၀၄၊ No. 18 Myaynigone Road, Sanchaung, Yangon မှန်ပါသလားရှင်။"),
        turn("customer", "ဟုတ်ကဲ့ အားလုံးမှန်ပါတယ်၊ အော်ဒါအတည်ပြုပေးပါရှင်။"),
    ]

    result = analyze_call(transcript, fallback_phone="+95961984204")

    assert result["customer"]["need"] == "2 ဘူး Venus BigOne ဝယ်မည်"
    assert result["order"] == {
        "customer_phone": "+95961984204",
        "customer_name": "Aung Min",
        "shipping_address": "No. 18 Myaynigone Road, Sanchaung, Yangon",
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
        turn("customer", "မဟုတ်ပါဘူးရှင်၊ ပို့ရမယ့် ဖုန်းနံပါတ်က ၀၉၆၁၆۹۵۴۴۸ ပါ။"),
        turn("agent", "ဖုန်းနံပါတ် ၀ ۹ ۶ ۱ ۶ ۹ ۵ ۴ ۴ ۸ က မှန်ပါသလားရှင်။"),
        turn("customer", "ဟုတ်ကဲ့ မှန်ပါတယ်ရှင်။"),
        turn("agent", "ပို့ဆောင်ရမယ့် လိပ်စာလေး ပြောပေးပါရှင်။"),
        turn("customer", "လိပ်စာက အမှတ် ၁၂၃၊ ဗိုလ်ချုပ်လမ်း၊ လသာမြို့နယ်၊ ရန်ကုန် ပါရှင်။"),
        turn("agent", "ကွန်ဘို ၃၊ May Thinzar၊ ၀۹۶۱۶۹۵۴۴۸၊ အမှတ် ၁۲۳ ဗိုလ်ချုပ်လမ်း လသာမြို့နယ် ရန်ကုန်ဆို မှန်ပါသလားရှင်။"),
        turn("customer", "ဟုတ်ကဲ့ အားလုံးမှန်ပါတယ်ရှင်။"),
    ]

    result = analyze_call(transcript, fallback_phone="+959771234567")

    assert result["customer"]["need"] == "Combo 3 ဝယ်မည်"
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
        turn("customer", "Combo 2 နဲ့ Combo 3 မှာ ဘာတွေပါလဲ။"),
        turn("agent", "Combo 2 က ၂ ဘူး၊ Combo 3 က ၃ ဘူးနဲ့ လက်ဆောင်ပါပါတယ်ရှင်။"),
        turn("customer", "Combo 2 ဝယ်မယ်။"),
        turn("customer", "ပြန်ပြင်မယ်၊ Combo 3 ဝယ်မယ်။"),
        turn("agent", "လက်ခံမယ့်နာမည်လေး ပြောပေးပါရှင်။"),
        turn("customer", "နာမည်က Ko Min ပါ။"),
        turn("customer", "နာမည်ကို Ko Min Naing လို့ ပြင်ပေးပါ။"),
        turn("agent", "ဖုန်းနံပါတ် ၀۹۰۱۱۱۲۲۳۳ မှန်ပါသလားရှင်။"),
        turn("customer", "မဟုတ်ပါဘူး၊ ဖုန်းနံပါတ်က 0987654321 ပါ။"),
        turn("agent", "၀၉၈၇၆۵۴۳۲۱ မှန်ပါသလားရှင်။"),
        turn("customer", "ဟုတ်ကဲ့ မှန်ပါတယ်။"),
        turn("customer", "လိပ်စာက Yangon Hlaing ပါ။"),
        turn("customer", "လိပ်စာကို ပြန်ပြင်ချင်ပါတယ်။"),
        turn("agent", "လိပ်စာအသစ် ပြောပေးပါရှင်။"),
        turn("customer", "လိပ်စာက Room 1208, Inya Road, Yangon ပါ။"),
        turn("agent", "အော်ဒါအချက်အလက်တွေ ပြန်ဖတ်ပြပါမယ်ရှင်။"),
        turn("customer", "ဟုတ်ကဲ့၊ နောက်ဆုံးပြင်ထားတဲ့ အချက်အလက်နဲ့ အတည်ပြုပေးပါ။"),
    ]

    result = analyze_call(transcript, fallback_phone="+95901112233")

    assert result["order"]["product_name"] == "Venus BigOne Combo 3"
    assert result["order"]["customer_name"] == "Ko Min Naing"
    assert result["order"]["customer_phone"] == "0987654321"
    assert result["order"]["shipping_address"] == "Room 1208, Inya Road, Yangon"
    assert result["order"]["missing_fields"] == []


def test_long_completed_details_are_not_an_order_after_customer_cancels() -> None:
    transcript = [
        turn("customer", "Combo 2 ဝယ်မယ်။"),
        turn("customer", "နာမည်က Hla Hla ပါ။"),
        turn("customer", "ဖုန်း 0912345678 ပါ။"),
        turn("customer", "လိပ်စာက No. 25 Pyay Road, Yangon ပါ။"),
        turn("agent", "အော်ဒါ Combo 2 ကို အချက်အလက်တွေနဲ့ အတည်ပြုပါမယ်ရှင်။"),
        turn("customer", "နေပါဦး၊ မဝယ်တော့ဘူး၊ အော်ဒါဖျက်ပေးပါ။"),
    ]

    result = analyze_call(transcript, fallback_phone="+95900000000")

    assert result["analysis"]["intent_status"] == "no_need"
    assert result["customer"]["need"] == "လိုအပ်ချက်မရှိ"
    assert result["order"] is None


def test_long_price_comparison_never_becomes_an_order_without_selection() -> None:
    transcript = [
        turn("customer", "တစ်ဘူးစျေးဘယ်လောက်လဲ။"),
        turn("agent", "တစ်ဘူး ၁၂၀၀၀၀ ကျပ်ပါရှင်။"),
        turn("customer", "၂ ဘူးဆို ဘယ်လောက်လဲ၊ ၃ ဘူးဆို ဘာလက်ဆောင်ပါလဲ။"),
        turn("agent", "Combo 2 က ၂၁၀၀၀၀ ကျပ်၊ Combo 3 က ၃၉၀၀၀၀ ကျပ်နဲ့ လက်ဆောင်ပါပါတယ်ရှင်။"),
        turn("customer", "Combo 5 ပို့ခအခမဲ့လား။"),
        turn("agent", "၂ ဘူးနှင့်အထက် ပို့ခအခမဲ့ပါရှင်။"),
        turn("customer", "စဉ်းစားနေတုန်းပါ၊ မမှာသေးပါဘူး။"),
    ]

    result = analyze_call(transcript, fallback_phone="+95961984204")

    assert result["analysis"]["intent_status"] == "considering"
    assert result["order"] is None


def test_outbound_rejection_never_creates_an_order() -> None:
    transcript = [
        turn("agent", "မင်္ဂလာပါရှင်။ Venus BigOne က ဆက်သွယ်တာပါ။ အခု ခဏပြောလို့ရမလားရှင်။"),
        turn("customer", "မလိုပါဘူး၊ စိတ်မဝင်စားဘူး၊ ဒီနံပါတ်ကို ထပ်မခေါ်ပါနဲ့။"),
        turn("agent", "နားလည်ပါတယ်ရှင်၊ အနှောင့်အယှက်ဖြစ်သွားရင် တောင်းပန်ပါတယ်။"),
    ]

    result = analyze_call(transcript, fallback_phone="+95961984204")

    assert result["analysis"]["intent_status"] == "no_need"
    assert result["order"] is None
