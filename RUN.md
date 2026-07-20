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

PostgreSQL data is stored in the Docker volume `voice_postgres_data`.
Use **Manage products** in the dashboard to configure product phone numbers,
greetings, knowledge, and offers without restarting the application.
