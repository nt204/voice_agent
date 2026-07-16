# Voice AI Sales

FastAPI backend for Myanmar-market AI inbound/outbound sales calls via Telnyx. It stores call history and transcripts, analyzes customer intent, and creates AI order records when a customer commits to buy.

## Run With Docker

Create `.env` from the sample if needed:

```bash
copy .env.example .env
```

Start the app:

```bash
docker compose up --build
```

Open the dashboard:

```text
http://localhost:3000/admin
```

## Main Endpoints

- `GET /` sales dashboard
- `GET /health` app health check
- `GET /api/calls` call list
- `GET /api/orders` AI order list
- `POST /telnyx/outbound/call` outbound Telnyx call
- `GET|POST /telnyx/answer` inbound call webhook
- `GET|POST /telnyx/outbound/answer` outbound call webhook

## Deployment Notes

- The app listens on port `3000` inside the container.
- The host maps port `3000` to the app container.
- SQLite call history is stored in the Docker volume `voice_app_data`.
- Do not commit real API keys in `.env`.
