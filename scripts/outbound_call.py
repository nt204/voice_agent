from dotenv import load_dotenv

from app.telnyx_client import create_outbound_call


def main() -> None:
    load_dotenv()
    print("--- TELNYX AI OUTBOUND CALL ---")
    to_number = input("Enter customer phone number (e.g., +959...): ").strip()
    from_number = input("Enter your Telnyx phone number, or leave blank for TELNYX_FROM_NUMBER: ").strip()
    if not to_number:
        raise SystemExit("Missing customer phone number")
    result = create_outbound_call(to_number, from_number or None)
    print("Call initiated successfully.")
    print(result)


if __name__ == "__main__":
    main()
