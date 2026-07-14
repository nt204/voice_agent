import urllib.request
import json
import sys

def main():
    url = "http://localhost:3000/api/calls/call-sim-myanmar-101"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            with open("scratch/call_detail_myanmar.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("Successfully saved call detail to scratch/call_detail_myanmar.json")
    except Exception as e:
        print(f"Error fetching call detail: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
