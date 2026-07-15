import os
import re
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/call_history.db")

def is_valid_name(name: str) -> bool:
    if not name:
        return True
    if len(name) > 30:
        return False
    if any(char in name for char in "?:;\"'()”’“‘"):
        return False
    if any(char.isdigit() for char in name):
        return False
    if any(char in name for char in "၀၁၂၃၄၅၆၇၈၉"):
        return False
    folded = name.casefold()
    latin_q_words = {"gì", "nào", "sao", "bao nhiêu", "ai", "đâu", "what", "who", "where", "how", "why"}
    if any(re.search(rf"\b{re.escape(w)}\b", folded) for w in latin_q_words):
        return False
    burmese_q_words = {"လဲ", "ဘယ်လောက်", "ဘာလဲ", "ဘယ်သူ", "ဘယ်မှာ", "လား"}
    if any(w in folded for w in burmese_q_words):
        return False
    return True

def is_valid_field(value: str) -> bool:
    if not value:
        return True
    if len(value) > 150:
        return False
    folded = value.casefold()
    question_patterns = [
        r"how can i", r"bye, i love you", r"what is", r"tên là gì",
        r"ဘယ်လောက် လဲ", r"ဘယ်သူလဲ", r"ဘာလဲ"
    ]
    if any(re.search(pat, folded) for pat in question_patterns):
        return False
    return True

def main():
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        # Clean calls table (names, needs, addresses)
        calls = conn.execute(text("SELECT id, customer_name, customer_need, customer_address FROM calls")).all()
        updated_calls = 0
        for call_id, name, need, address in calls:
            new_name = "" if name and not is_valid_name(name) else name
            new_need = "" if need and not is_valid_field(need) else need
            new_address = "" if address and not is_valid_field(address) else address
            
            if new_name != name or new_need != need or new_address != address:
                print(f"Cleaning call {call_id}:")
                if new_name != name:
                    print(f"  name: {name!r} -> {new_name!r}")
                if new_need != need:
                    print(f"  need: {need!r} -> {new_need!r}")
                if new_address != address:
                    print(f"  address: {address!r} -> {new_address!r}")
                conn.execute(
                    text("UPDATE calls SET customer_name = :name, customer_need = :need, customer_address = :address WHERE id = :id"),
                    {"name": new_name, "need": new_need, "address": new_address, "id": call_id}
                )
                updated_calls += 1
        
        # Clean orders table
        orders = conn.execute(text("SELECT id, customer_name FROM orders")).all()
        updated_orders = 0
        for order_id, name in orders:
            new_name = "" if name and not is_valid_name(name) else name
            if new_name != name:
                print(f"Cleaning order {order_id}:")
                print(f"  name: {name!r} -> {new_name!r}")
                conn.execute(
                    text("UPDATE orders SET customer_name = :name WHERE id = :id"),
                    {"name": new_name, "id": order_id}
                )
                updated_orders += 1
                
        print(f"Cleanup complete. Updated {updated_calls} calls and {updated_orders} orders.")

if __name__ == "__main__":
    main()
