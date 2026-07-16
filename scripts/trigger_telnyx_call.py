import argparse
import sys
import httpx

def main():
    parser = argparse.ArgumentParser(description="Trigger an outbound Telnyx call using the FastAPI server.")
    parser.add_argument("to_number", help="Destination phone number (e.g., +95901234567, +84901234567, 84..., or 'VN 09...')")
    parser.add_argument("--from-number", help="Optional caller ID to use instead of default in config")
    parser.add_argument("--url", default="http://localhost:3000/telnyx/outbound/call", help="FastAPI Server endpoint (default: http://localhost:3000/telnyx/outbound/call)")

    args = parser.parse_args()

    payload = {
        "to_number": args.to_number
    }
    if args.from_number:
        payload["from_number"] = args.from_number

    print(f"Triggering outbound call to {args.to_number} via {args.url}...")
    try:
        response = httpx.post(args.url, json=payload, timeout=15.0)
        print(f"Server Response Status: {response.status_code}")
        try:
            res_data = response.json()
            if response.status_code == 200 and res_data.get("ok"):
                print("Call triggered successfully!")
                print(f"Call SID: {res_data.get('call_sid')}")
            else:
                print("Failed to trigger call:")
                print(res_data.get("error", res_data))
        except Exception:
            print("Response content (non-JSON):")
            print(response.text)
    except Exception as e:
        print(f"HTTP Request failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
