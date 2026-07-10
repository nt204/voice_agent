import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.call_history import (
    CallHistoryStore,
    classify_customer_interest,
    extract_customer_info,
)
import app.main as main


class CustomerExtractionTests(unittest.TestCase):
    def test_classifies_customer_who_wants_advice(self) -> None:
        transcript = [
            {"speaker": "agent", "text": "Anh có cần tư vấn không?"},
            {"speaker": "customer", "text": "Tôi muốn được tư vấn thêm về cách dùng."},
        ]

        self.assertEqual(classify_customer_interest(transcript), "needs_consultation")

    def test_classifies_customer_who_has_no_current_need(self) -> None:
        transcript = [
            {"speaker": "customer", "text": "Hiện tại tôi chưa có nhu cầu, cảm ơn."},
        ]

        self.assertEqual(classify_customer_interest(transcript), "no_need")

    def test_does_not_infer_interest_from_agent_speech(self) -> None:
        transcript = [
            {"speaker": "agent", "text": "Chị có muốn mua và cần tư vấn thêm không?"},
            {"speaker": "customer", "text": "Tôi nghe máy đây."},
        ]

        self.assertEqual(classify_customer_interest(transcript), "unknown")

    def test_extracts_only_customer_supplied_contact_details(self) -> None:
        transcript = [
            {"speaker": "agent", "text": "Số điện thoại của anh là 0900000000 phải không?"},
            {
                "speaker": "customer",
                "text": "Tôi tên Nguyễn Văn An, số điện thoại 0912 345 678, "
                "địa chỉ 12 Nguyễn Trãi, Hà Nội. Tôi muốn mua 2 hộp.",
            },
        ]

        result = extract_customer_info(transcript)

        self.assertEqual(result["name"], "Nguyễn Văn An")
        self.assertEqual(result["phone"], "0912 345 678")
        self.assertEqual(result["address"], "12 Nguyễn Trãi, Hà Nội")
        self.assertEqual(result["need"], "mua 2 hộp")
        self.assertNotIn("0900000000", result.values())

    def test_returns_empty_fields_when_customer_does_not_provide_information(self) -> None:
        result = extract_customer_info(
            [{"speaker": "customer", "text": "Tôi chỉ hỏi giá sản phẩm thôi."}]
        )

        self.assertEqual(
            result,
            {"name": "", "phone": "", "address": "", "need": "", "notes": ""},
        )

    def test_extracts_common_myanmar_customer_details(self) -> None:
        result = extract_customer_info(
            [
                {
                    "speaker": "customer",
                    "text": "ကျွန်မနာမည်က စုစု၊ ဖုန်းနံပါတ် 0912345678၊ "
                    "လိပ်စာက ရန်ကုန်မြို့။ Calcium Gold ဝယ်ချင်ပါတယ်။",
                }
            ]
        )

        self.assertEqual(result["name"], "စုစု")
        self.assertEqual(result["phone"], "0912345678")
        self.assertEqual(result["address"], "ရန်ကုန်မြို့")
        self.assertIn("ဝယ်ချင်", result["need"])


class CallHistoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = CallHistoryStore(Path(self.temp_dir.name) / "calls.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_persists_direction_transcript_and_extracted_customer(self) -> None:
        self.store.start_call(
            call_id="call-1",
            direction="outbound",
            provider="telnyx",
            customer_phone="+84912345678",
        )
        self.store.add_transcript("call-1", "customer", "Tôi tên Lan, tôi muốn mua 1 hộp.")
        self.store.add_transcript("call-1", "agent", "Cảm ơn chị Lan.")

        self.store.finish_call("call-1")
        call = self.store.get_call("call-1")

        self.assertEqual(call["direction"], "outbound")
        self.assertEqual(call["status"], "completed")
        self.assertEqual(call["customer"]["name"], "Lan")
        self.assertEqual(call["customer"]["phone"], "+84912345678")
        self.assertEqual(call["interest_status"], "needs_consultation")
        self.assertEqual(len(call["transcript"]), 2)
        self.assertIsNotNone(call["ended_at"])

    def test_lists_calls_filtered_by_direction(self) -> None:
        self.store.start_call("in-1", "inbound", "signalwire")
        self.store.start_call("out-1", "outbound", "telnyx")

        result = self.store.list_calls(direction="outbound")

        self.assertEqual([call["id"] for call in result], ["out-1"])

    def test_lists_calls_filtered_by_interest_status(self) -> None:
        self.store.start_call("need-1", "inbound", "telnyx")
        self.store.add_transcript("need-1", "customer", "Tôi cần tư vấn thêm.")
        self.store.finish_call("need-1")
        self.store.start_call("no-need-1", "inbound", "telnyx")
        self.store.add_transcript("no-need-1", "customer", "Tôi chưa có nhu cầu.")
        self.store.finish_call("no-need-1")

        result = self.store.list_calls(interest_status="no_need")

        self.assertEqual([call["id"] for call in result], ["no-need-1"])


class CallHistoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_store = main.call_history
        main.call_history = CallHistoryStore(Path(self.temp_dir.name) / "calls.db")
        main.call_history.start_call("api-call", "inbound", "telnyx", "+959123456")
        main.call_history.add_transcript("api-call", "customer", "Tôi tên Mai.")
        main.call_history.finish_call("api-call")
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.call_history = self.original_store
        self.temp_dir.cleanup()

    def test_dashboard_and_api_expose_saved_calls(self) -> None:
        dashboard = self.client.get("/")
        listing = self.client.get("/api/calls?direction=inbound")
        detail = self.client.get("/api/calls/api-call")

        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Lịch sử cuộc gọi", dashboard.text)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["calls"][0]["id"], "api-call")
        self.assertEqual(detail.json()["customer"]["name"], "Mai")
        self.assertIn("interest_counts", listing.json())


if __name__ == "__main__":
    unittest.main()
