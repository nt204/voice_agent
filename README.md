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

## Manage Multiple Products

Use **Manage products** in the dashboard to add or edit:

- the Telnyx phone number and optional TeXML App ID;
- inbound and outbound greetings;
- product-specific AI instructions and knowledge;
- offers, quantities, prices, and shipping policies;
- language, voice, active state, and the default product.

For outbound calls, select a product before entering the customer phone number.
For inbound calls, the app selects the product mapped to the called Telnyx number.
Product changes apply to future calls; existing calls and order price snapshots remain unchanged.

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
- PostgreSQL stores call history, products, offers, and orders in the `postgres_data` volume.
- SQLite remains available as the local fallback when `DATABASE_URL` is not supplied by Docker Compose.
- Do not commit real API keys in `.env`.
