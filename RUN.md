# Hướng Dẫn Chạy Nhanh

## 1. Cài môi trường

```bash
cd "/Users/macbook/Desktop/Viber call"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Chạy PostgreSQL

Mở Docker Desktop trước, rồi chạy:

```bash
docker compose up -d postgres
```

Trong `.env`, dùng:

```bash
DATABASE_URL=postgresql+psycopg://telnyx:telnyx_password@localhost:5432/telnyx_calls
```

Nếu chưa chạy PostgreSQL, có thể tạm dùng SQLite:

```bash
DATABASE_URL=sqlite:///recordings.db
```

## 3. Chạy backend

```bash
source .venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000
```

Health check:

```text
http://localhost:3000/health
```

## 4. Public URL bằng ngrok

```bash
ngrok http 3000
```

Copy HTTPS URL vào `.env`:

```bash
PUBLIC_BASE_URL=https://your-ngrok-domain.ngrok-free.app
```

Restart backend sau khi đổi `.env`.

## 5. Cấu hình Telnyx

Trong Telnyx TeXML app hoặc inbound number webhook:

```text
Voice webhook URL: https://your-ngrok-domain/telnyx/answer
Method: POST
```

## 6. Web quản lý

```text
http://localhost:3000/admin
```

Nếu đặt `ADMIN_TOKEN` trong `.env`:

```text
http://localhost:3000/admin?token=YOUR_TOKEN
```

Web quản lý dùng để nghe inbound/outbound WAV, xem log, xem intent, chạy lại extract, cleanup recording cũ, xem thống kê sales và export CSV.

## 7. Gọi outbound bằng AI

Từ terminal:

```bash
python3 -m scripts.outbound_call
```

Hoặc mở web admin và dùng form **Call Out**.

Nếu muốn không nhập số gọi đi mỗi lần, đặt trong `.env`:

```bash
TELNYX_FROM_NUMBER=+1_your_telnyx_number
```

Outbound sẽ dùng webhook:

```text
https://<PUBLIC_BASE_URL>/telnyx/answer?direction=outbound-ai
```

## 8. File ghi âm

```text
recordings/inbound/<phone>_<timestamp>.wav
recordings/outbound/<phone>_<timestamp>.wav
recordings/logs/<phone>_<timestamp>.log
```

Metadata, transcript và intent lưu trong database.

## 9. Test

```bash
python3 -m pytest
```

lsof -ti tcp:3000 | xargs kill -9