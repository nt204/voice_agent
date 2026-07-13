# Chạy dự án

Chỉ cần Docker Desktop và file `.env`.

```bash
docker compose up --build
```

Mở giao diện:

```text
http://localhost:3000/admin
```

Compose map cố định cổng máy host `3000` vào cổng app `3000` trong container.

Database lịch sử cuộc gọi được lưu trong Docker volume `voice_app_data`.
