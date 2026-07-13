# Chạy dự án

Chỉ cần Docker Desktop và file `.env`.

```bash
docker compose up --build
```

Mở giao diện:

```text
http://localhost:3001
```

Mặc định compose map cổng máy host `3001` vào cổng app `3000` trong container để tránh đụng các process cũ đang giữ port 3000.

Nếu muốn đổi cổng:

```bash
APP_PORT=3002 docker compose up --build
```

Database lịch sử cuộc gọi được lưu trong Docker volume `voice_app_data`.
