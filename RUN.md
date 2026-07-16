# Run The Project

You only need Docker Desktop and a `.env` file.

```bash
docker compose up --build
```

Open the dashboard:

```text
http://localhost:3000/admin
```

Compose maps host port `3000` to app port `3000` in the container.

Call-history data is stored in the Docker volume `voice_app_data`.
