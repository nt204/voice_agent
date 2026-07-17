import json
from dotenv import load_dotenv
from app.config import config
from app.order_extraction import analyze_call_with_gemini

# Load environment variables from .env
load_dotenv()

def run_test():
    print("Running Complex Dialogue Extraction Test with Live Gemini...")
    
    # Verify API key
    if not config.gemini.api_key:
        print("Error: GEMINI_API_KEY is not configured in .env file.")
        return

    # A long, difficult, and realistic conversation transcript in Burmese
    transcript = [
        {"speaker": "agent", "text": "မင်္ဂလာပါ။ Venus BigOne နို့မှုန့် အကြောင်း မေးလို့ရပါတယ်ရှင်။"},
        {"speaker": "customer", "text": "နို့မှုန့်က ဘာကောင်းလဲ။ အမျိုးသမီးတွေအတွက်ပဲလား။ ဈေးကရော ဘယ်လောက်လဲ။"},
        {"speaker": "agent", "text": "ဟုတ်ကဲ့ပါရှင်။ အမျိုးသမီးတွေအတွက် အထူးထုတ်လုပ်ထားပြီး အသားအရေနဲ့ ခန္ဓာကိုယ်လှပဖို့ သောက်သုံးနိုင်ပါတယ်ရှင်။ တစ်ဘူးကို တစ်သိန်းနှစ်သောင်းကျပ်ပါရှင်။"},
        {"speaker": "customer", "text": "စျေးကြီးတယ်နော်။ တခြား ကွန်ဘိုတွေ မရှိဘူးလား။ ငါးဘူးဝယ်ရင် ဘယ်လောက်လဲ။"},
        {"speaker": "agent", "text": "၅ ဘူးဆိုရင် Combo 5 ပါရှင်။ စုစုပေါင်း ၆ သိန်း ၃ သောင်းကျပ် ကျသင့်ပြီး Venus နို့မှုန့် ၂ ဘူးနဲ့ Venus effervescent tablets ၂ ဘူး လက်ဆောင်ပါရှင်။ ပို့ခအခမဲ့ပါရှင်။"},
        {"speaker": "customer", "text": "ကွန်ဘို ၅ က တအားများတယ်။ ကွန်ဘို ၃ ယူမယ်။ မဟုတ်ဘူး၊ စဉ်းစားဦးမယ်... ကွန်ဘို ၃ မှာ ၃ ဘူးပါတယ်။ စျေးက ၃ သိန်း ၉ သောင်းနော်။ ဟုတ်လား။"},
        {"speaker": "agent", "text": "ဟုတ်ကဲ့ပါရှင်။ Combo 3 က ၃ ဘူးအတွက် ၃ သိန်း ၉ သောင်းကျပ်ဖြစ်ပြီး Venus နို့မှုန့် ၁ ဘူးနဲ့ Venus effervescent tablets ၁ ဘူး လက်ဆောင်ပါရှင်။"},
        {"speaker": "customer", "text": "အေး အဲ့ဒါဆို ကွန်ဘို ၃ ပဲ မှာယူမယ်။"},
        {"speaker": "agent", "text": "ဟုတ်ကဲ့ပါရှင်။ ဖုန်းနံပါတ်နဲ့ ပို့ရမယ့် လိပ်စာလေး ပြောပေးပါဦးရှင်။"},
        {"speaker": "customer", "text": "ဖုန်းနံပါတ်က ၀၉၇၈၄၄၃၃၅၅၆ ပါ။ လိပ်စာကတော့ ရန်ကုန်မြို့၊ ကမာရွတ်မြို့နယ်၊ လှည်းတန်းလမ်း၊ အမှတ် ၁၂၃၊ ဒုတိယထပ်ပါ။"},
        {"speaker": "agent", "text": "ဟုတ်ကဲ့ပါရှင်။ ဖုန်း ၀၉၇၈၄၄၃၃၅၅၆၊ ပို့ရမယ့်လိပ်စာကတော့ ရန်ကုန်၊ ကမာရွတ်၊ လှည်းတန်းလမ်း၊ အမှတ် ၁၂၃၊ ဒုတိယထပ်၊ မှာယူတဲ့ပစ္စည်းက Combo 3 (၃ ဘူး)၊ စုစုပေါင်း ကျသင့်ငွေ ၃ သိန်း ၉ သောင်းကျပ်ပါရှင်။ ဟုတ်ပါသလားရှင်။"},
        {"speaker": "customer", "text": "ဟုတ်ကဲ့၊ အဲဒါ အမှန်ပဲ။ ပို့ပေးလိုက်ပါ။"}
    ]
    
    # Run the live Gemini extraction
    result = analyze_call_with_gemini(transcript, fallback_phone="")
    
    print("\n==========================================")
    print("EXTRACTED RESULTS FROM GEMINI LIVE PROMPT")
    print("==========================================")
    print("\n--- Customer Demographics & Need ---")
    print(json.dumps(result.get("customer", {}), ensure_ascii=False, indent=2))
    
    print("\n--- Sales Intent & Objection Analysis ---")
    print(json.dumps(result.get("analysis", {}), ensure_ascii=False, indent=2))
    
    print("\n--- Extracted Order Details ---")
    print(json.dumps(result.get("order", {}), ensure_ascii=False, indent=2))
    print("==========================================\n")

if __name__ == "__main__":
    run_test()
