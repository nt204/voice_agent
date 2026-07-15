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
            "intent_status": "considering",
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
    return _run_scenario_with_direction(store, scenario, "outbound")


def _run_scenario_with_direction(store: CallHistoryStore, scenario: dict, direction: str) -> dict:
    call_id = scenario["id"]
    store.start_call(
        call_id=call_id,
        direction=direction,
        provider="scenario-test",
        customer_phone=scenario.get("customer_phone", ""),
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


MYANMAR_PARSER_CASES = [
    {
        "id": "my-parser-combo-2-complete",
        "customer_phone": "",
        "turns": [
            ("agent", "Venus BigOne ကို ဘယ်လိုကူညီပေးရမလဲရှင်။"),
            (
                "customer",
                "ကွန်ဘို ၂ မှာယူမယ်။ ဖုန်း ၀၉၆၁၆၉၅၄၄၈ ပါ။ လိပ်စာ Mandalay Chan Aye Tharzan ပါ။ အသက် ၂၈ အမျိုးသမီးပါ။",
            ),
        ],
        "expected": {
            "intent_status": "ready_to_order",
            "order_status": "ready_to_confirm",
            "product_name": "Venus BigOne Combo 2",
            "quantity": 2,
            "phone": "0961695448",
            "address": "Mandalay Chan Aye Tharzan",
            "total_price": 210000,
            "gender": "female",
            "age_range": "25-34",
        },
    },
    {
        "id": "my-parser-combo-1-missing-address",
        "customer_phone": "+959771234567",
        "turns": [
            ("agent", "Combo အကြောင်း မေးလို့ရပါတယ်ရှင်။"),
            ("customer", "ကွန်ဘို နံပါတ် ၁ ယူမယ်။ စျေးဘယ်လောက်လဲ။"),
        ],
        "expected": {
            "intent_status": "ready_to_order",
            "order_status": "missing_info",
            "product_name": "Venus BigOne Combo 1",
            "quantity": 1,
            "phone": "+959771234567",
            "total_price": 120000,
            "missing_fields": ["shipping_address"],
        },
    },
    {
        "id": "my-parser-split-order-complete",
        "customer_phone": "",
        "turns": [
            ("agent", "Venus BigOne ကို ဘယ်လိုကူညီပေးရမလဲရှင်။"),
            ("customer", "ကွန်ဘို ၂ မှာယူမယ်။"),
            ("agent", "ဖုန်းနံပါတ်လေး ပြောပေးပါရှင်။"),
            ("customer", "ဖုန်း ၀၉၆၁၆۹۵۴۴۸ ပါ။"),
            ("agent", "ပို့ရန်လိပ်စာလေး ပြောပေးပါရှင်။"),
            ("customer", "လိပ်စာ Mandalay Chan Aye Tharzan ပါ။"),
        ],
        "expected": {
            "intent_status": "ready_to_order",
            "order_status": "ready_to_confirm",
            "product_name": "Venus BigOne Combo 2",
            "quantity": 2,
            "phone": "0961695448",
            "address": "Mandalay Chan Aye Tharzan",
            "total_price": 210000,
        },
    },
    {
        "id": "my-parser-regular-two-boxes",
        "customer_phone": "",
        "turns": [
            ("agent", "နို့မှုန့်မှာယူချင်ရင် ပြောပေးပါရှင်။"),
            (
                "customer",
                "Venus နို့မှုန့် နှစ်ဘူး ဝယ်ယူမယ်။ ဖုန်း ၀၉၇၇၇၇၇၇၇၇၇ ပါ။ ပို့ရန်လိပ်စာ Yangon Hlaing ပါ။",
            ),
        ],
        "expected": {
            "intent_status": "ready_to_order",
            "order_status": "ready_to_confirm",
            "product_name": "Venus BigOne",
            "quantity": 2,
            "phone": "09777777777",
            "address": "Yangon Hlaing",
            "total_price": 240000,
        },
    },
    {
        "id": "my-parser-price-only-no-order",
        "customer_phone": "+959771234567",
        "turns": [
            ("agent", "မင်္ဂလာပါရှင်။"),
            ("customer", "ကွန်ဘို ၂ စျေး ဘယ်လောက်လဲ။"),
        ],
        "expected": {
            "intent_status": "price_checking",
            "order_status": None,
        },
    },
    {
        "id": "my-parser-not-interested",
        "customer_phone": "+959771234567",
        "turns": [
            ("agent", "Venus BigOne အကြောင်း မိတ်ဆက်ပေးပါမယ်ရှင်။"),
            ("customer", "မလိုဘူး။ စိတ်မဝင်စားပါဘူး။"),
        ],
        "expected": {
            "intent_status": "no_need",
            "order_status": None,
        },
    },
]


def test_myanmar_parser_cases_cover_inbound_and_outbound(tmp_path: Path):
    store = CallHistoryStore(tmp_path / "call_history.db")

    for direction in ("inbound", "outbound"):
        for base_case in MYANMAR_PARSER_CASES:
            case = {**base_case, "id": f"{direction}-{base_case['id']}"}
            call = _run_scenario_with_direction(store, case, direction)
            expected = case["expected"]

            assert call["direction"] == direction, case["id"]
            assert call["analysis"]["intent_status"] == expected["intent_status"], case["id"]
            order_status = call["order"]["status"] if call["order"] else None
            assert order_status == expected["order_status"], case["id"]

            if expected.get("product_name"):
                assert call["order"]["product_name"] == expected["product_name"], case["id"]
            if expected.get("quantity"):
                assert call["order"]["quantity"] == expected["quantity"], case["id"]
            if expected.get("phone"):
                assert call["order"]["customer_phone"] == expected["phone"], case["id"]
            if expected.get("address"):
                assert call["customer"]["address"] == expected["address"], case["id"]
                assert call["order"]["shipping_address"] == expected["address"], case["id"]
            if expected.get("total_price"):
                assert call["order"]["total_price"] == expected["total_price"], case["id"]
            if expected.get("missing_fields"):
                assert call["order"]["missing_fields"] == expected["missing_fields"], case["id"]
            if expected.get("gender"):
                assert call["analysis"]["gender"] == expected["gender"], case["id"]
            if expected.get("age_range"):
                assert call["analysis"]["age_range"] == expected["age_range"], case["id"]
