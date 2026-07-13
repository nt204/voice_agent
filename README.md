# Voice AI Sales

Backend FastAPI cho AI gọi vào/gọi ra qua Telnyx, lưu lịch sử cuộc gọi, transcript, phân tích nhu cầu khách hàng và tự tạo đơn hàng AI khi khách chốt mua.

## Chạy bằng một lệnh Docker

Tạo `.env` từ mẫu nếu chưa có:

```bash
copy .env.example .env
```

Chạy app:

```bash
docker compose up --build
```

Mở dashboard:

```text
http://localhost:3001
```

## Endpoint chính

- `GET /` dashboard quản lý sales
- `GET /health` kiểm tra app
- `GET /api/calls` danh sách cuộc gọi
- `GET /api/orders` danh sách đơn hàng AI
- `POST /telnyx/outbound/call` gọi ra qua Telnyx
- `GET|POST /telnyx/answer` webhook gọi vào
- `GET|POST /telnyx/outbound/answer` webhook gọi ra

## Ghi chú triển khai

- App chạy trong container ở cổng `3000`.
- Máy host mặc định mở ở `3001` để tránh đụng port local cũ.
- Dữ liệu SQLite được lưu trong Docker volume `voice_app_data`.
- Không commit API key thật trong `.env`.
