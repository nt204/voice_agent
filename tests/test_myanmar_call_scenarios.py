from pathlib import Path

from app.call_history import CallHistoryStore


SCENARIOS = [
    {
        "id": "my-buy-complete",
        "description": "Customer asks product details, buys, gives phone and address.",
        "turns": [
            ("agent", "မင်္ဂလာပါရှင်။ Venus BigOne အကြောင်း မေးလို့ရပါတယ်ရှင်။"),
            ("customer", "Venus BigOne က ဘာအတွက်သောက်တာလဲ၊ ဈေးဘယ်လောက်လဲ။"),
            ("agent", "အမျိုးသမီးအလှအပနဲ့ ခန္ဓာကိုယ်ထိန်းသိမ်းမှုအတွက် အထောက်အကူပြုတဲ့ နို့မှုန့်ပါရှင်။ တစ်ဘူးကို တစ်သိန်းနှစ်သောင်းကျပ်ပါ။"),
            ("customer", "စိတ်ဝင်စားတယ်။ Venus BigOne 2 ဘူး မှာမယ်။"),
            ("agent", "ဖုန်းနံပါတ်လေး ပြောပေးနိုင်မလားရှင်။"),
            ("customer", "ဖုန်း 0961695448 ပါ။"),
            ("agent", "ပို့ရမယ့် လိပ်စာလေး ပြောပေးပါရှင်။"),
            ("customer", "လိပ်စာ Yangon Hledan, Insein Road ပါ။ အသက် 28 အမျိုးသမီးပါ။"),
        ],
        "expected": {
            "interest_status": "needs_consultation",
            "intent_status": "ready_to_order",
            "order_status": "ready_to_confirm",
            "quantity": 2,
            "phone": "0961695448",
            "address": "Yangon Hledan, Insein Road",
            "product_name": "Venus BigOne",
            "total_price": 240000,
            "gender": "female",
            "age_range": "25-34",
        },
    },
    {
        "id": "my-consultation-no-order-yet",
        "description": "Customer is interested and wants advice but has not ordered.",
        "turns": [
            ("agent", "Venus BigOne အကြောင်း ဘာသိချင်ပါသလဲရှင်။"),
            ("customer", "အသက် 30 အမျိုးသမီးပါ။ သောက်နည်းနဲ့ ဘေးထွက်ဆိုးကျိုး ရှိမရှိ သိချင်ပါတယ်။"),
            ("agent", "တစ်နေ့နှစ်ခွက် သောက်နိုင်ပါတယ်ရှင်။ ရောဂါအခံရှိရင် ဆရာဝန်နဲ့ အရင်တိုင်ပင်ပါ။"),
            ("customer", "အိုကေ၊ စိတ်ဝင်စားပါတယ် ဒါပေမယ့် အခု မမှာသေးဘူး၊ နောက်မှပြန်ဆက်ပါ။"),
        ],
        "expected": {
            "interest_status": "needs_consultation",
            "intent_status": "needs_consultation",
            "order_status": None,
            "gender": "female",
            "age_range": "25-34",
        },
    },
    {
        "id": "my-not-interested",
        "description": "Customer clearly does not want to buy.",
        "turns": [
            ("agent", "Venus BigOne နို့မှုန့်အကြောင်း မိတ်ဆက်ပေးပါမယ်ရှင်။"),
            ("customer", "မလိုချင်ပါဘူး။ အခု မဝယ်ချင်ဘူး၊ စိတ်မဝင်စားပါဘူး။"),
            ("agent", "ရပါတယ်ရှင်။ နောက်လိုအပ်ရင် ပြန်ဆက်သွယ်နိုင်ပါတယ်။"),
        ],
        "expected": {
            "interest_status": "no_need",
            "intent_status": "no_need",
            "order_status": None,
        },
    },
    {
        "id": "my-considering-price-objection",
        "description": "Customer asks price/combo and remains hesitant.",
        "turns": [
            ("agent", "Venus BigOne ကို ဘယ်လိုကူညီပေးရမလဲရှင်။"),
            ("customer", "Combo ဈေးလေး သိချင်တယ်။ 2 ဘူးဝယ်ရင် ဘယ်လောက်လဲ။"),
            ("agent", "2 ဘူးကို 2 သိန်း 1 သောင်းကျပ်ပါရှင်။ 2 ဘူးနဲ့အထက် ပို့ခအခမဲ့ပါ။"),
            ("customer", "စျေးနည်းနည်းများတယ်။ စဉ်းစားဦးမယ်၊ အိမ်ကလူနဲ့ တိုင်ပင်ပြီးမှ ဆုံးဖြတ်မယ်။"),
        ],
        "expected": {
            "interest_status": "needs_consultation",
            "intent_status": "considering",
            "order_status": None,
            "objection": "price",
        },
    },
]


def _run_scenario(store: CallHistoryStore, scenario: dict) -> dict:
    call_id = scenario["id"]
    store.start_call(
        call_id=call_id,
        direction="outbound",
        provider="scenario-test",
        customer_phone="",
    )
    for speaker, text in scenario["turns"]:
        store.add_transcript(call_id, speaker, text)
    store.finish_call(call_id)
    call = store.get_call(call_id)
    assert call is not None
    return call


def test_myanmar_customer_scenarios_cover_real_sales_outcomes(tmp_path: Path):
    store = CallHistoryStore(tmp_path / "call_history.db")

    for scenario in SCENARIOS:
        call = _run_scenario(store, scenario)
        expected = scenario["expected"]

        assert call["status"] == "completed", scenario["id"]
        assert [item["speaker"] for item in call["transcript"]] == [
            speaker for speaker, _ in scenario["turns"]
        ], scenario["id"]
        assert [item["text"] for item in call["transcript"]] == [
            text for _, text in scenario["turns"]
        ], scenario["id"]
        assert call["interest_status"] == expected["interest_status"], scenario["id"]
        assert call["analysis"]["intent_status"] == expected["intent_status"], scenario["id"]

        order_status = call["order"]["status"] if call["order"] else None
        assert order_status == expected["order_status"], scenario["id"]
        if expected.get("quantity"):
            assert call["order"]["quantity"] == expected["quantity"], scenario["id"]
        if expected.get("phone"):
            assert call["order"]["customer_phone"] == expected["phone"], scenario["id"]
        if expected.get("address"):
            assert call["customer"]["address"] == expected["address"], scenario["id"]
            assert call["order"]["shipping_address"] == expected["address"], scenario["id"]
        if expected.get("product_name"):
            assert call["order"]["product_name"] == expected["product_name"], scenario["id"]
        if expected.get("total_price"):
            assert call["order"]["total_price"] == expected["total_price"], scenario["id"]
        if expected.get("gender"):
            assert call["analysis"]["gender"] == expected["gender"], scenario["id"]
        if expected.get("age_range"):
            assert call["analysis"]["age_range"] == expected["age_range"], scenario["id"]
        if expected.get("objection"):
            assert call["analysis"]["objection"] == expected["objection"], scenario["id"]
