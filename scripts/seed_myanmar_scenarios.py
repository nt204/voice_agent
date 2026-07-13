import argparse
import sqlite3
from pathlib import Path

from app.call_history import CallHistoryStore


SCENARIOS = [
    {
        "id": "my-buy-complete-ui",
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
    },
    {
        "id": "my-consultation-no-order-ui",
        "turns": [
            ("agent", "Venus BigOne အကြောင်း ဘာသိချင်ပါသလဲရှင်။"),
            ("customer", "အသက် 30 အမျိုးသမီးပါ။ သောက်နည်းနဲ့ ဘေးထွက်ဆိုးကျိုး ရှိမရှိ သိချင်ပါတယ်။"),
            ("agent", "တစ်နေ့နှစ်ခွက် သောက်နိုင်ပါတယ်ရှင်။ ရောဂါအခံရှိရင် ဆရာဝန်နဲ့ အရင်တိုင်ပင်ပါ။"),
            ("customer", "အိုကေ၊ စိတ်ဝင်စားပါတယ် ဒါပေမယ့် အခု မမှာသေးဘူး၊ နောက်မှပြန်ဆက်ပါ။"),
        ],
    },
    {
        "id": "my-not-interested-ui",
        "turns": [
            ("agent", "Venus BigOne နို့မှုန့်အကြောင်း မိတ်ဆက်ပေးပါမယ်ရှင်။"),
            ("customer", "မလိုချင်ပါဘူး။ အခု မဝယ်ချင်ဘူး၊ စိတ်မဝင်စားပါဘူး။"),
            ("agent", "ရပါတယ်ရှင်။ နောက်လိုအပ်ရင် ပြန်ဆက်သွယ်နိုင်ပါတယ်။"),
        ],
    },
    {
        "id": "my-considering-price-ui",
        "turns": [
            ("agent", "Venus BigOne ကို ဘယ်လိုကူညီပေးရမလဲရှင်။"),
            ("customer", "Combo ဈေးလေး သိချင်တယ်။ 2 ဘူးဝယ်ရင် ဘယ်လောက်လဲ။"),
            ("agent", "2 ဘူးကို 2 သိန်း 1 သောင်းကျပ်ပါရှင်။ 2 ဘူးနဲ့အထက် ပို့ခအခမဲ့ပါ။"),
            ("customer", "စျေးနည်းနည်းများတယ်။ စဉ်းစားဦးမယ်၊ အိမ်ကလူနဲ့ တိုင်ပင်ပြီးမှ ဆုံးဖြတ်မယ်။"),
        ],
    },
]


def clear_existing(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for scenario in SCENARIOS:
            connection.execute("DELETE FROM orders WHERE call_id = ?", (scenario["id"],))
            connection.execute("DELETE FROM call_analysis WHERE call_id = ?", (scenario["id"],))
            connection.execute("DELETE FROM transcripts WHERE call_id = ?", (scenario["id"],))
            connection.execute("DELETE FROM calls WHERE id = ?", (scenario["id"],))


def seed(db_path: Path) -> None:
    clear_existing(db_path)
    store = CallHistoryStore(db_path)
    for scenario in SCENARIOS:
        store.start_call(scenario["id"], "outbound", "scenario-test", "")
        for speaker, text in scenario["turns"]:
            store.add_transcript(scenario["id"], speaker, text)
        store.finish_call(scenario["id"])
        print(f"seeded {scenario['id']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/call_history.db")
    args = parser.parse_args()
    seed(Path(args.db))


if __name__ == "__main__":
    main()
