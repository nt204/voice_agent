# Spec: Call history and customer extraction

## Objective

Add an operator dashboard that persists every AI call, separates inbound and
outbound calls, shows the transcript, and extracts customer details only when
the caller provides them. Calls are also separated into needs consultation,
no current need, and unknown interest.

## Tech Stack

- Existing FastAPI application and Gemini Live bridge
- Python standard-library SQLite for durable local storage
- Server-rendered HTML, CSS, and small vanilla JavaScript dashboard

## Commands

- Test: `python -m unittest discover -s tests -v`
- Run: `python -m uvicorn app.main:app --host 0.0.0.0 --port 3000`
- Check: `Invoke-RestMethod http://localhost:3000/health`

## Project Structure

- `app/call_history.py`: persistence, transcript, extraction, query logic
- `app/gemini_bridge.py`: emits transcript events
- `app/main.py`: call lifecycle and dashboard/API routes
- `app/static/`: dashboard assets
- `tests/`: unit and API tests

## Code Style

Use typed Python with small standard-library components:

```python
store.start_call(call_id="call-1", direction="inbound", provider="telnyx")
store.add_transcript(call_id="call-1", speaker="customer", text="Tôi tên An")
store.finish_call("call-1")
```

## Testing Strategy

- Unit tests use a temporary SQLite database.
- API tests exercise list/detail endpoints and the dashboard.
- Existing bridge tests remain green.
- Runtime smoke test checks health, dashboard, and a complete persisted call.

## Boundaries

- Always: preserve current Telnyx, SignalWire, and Infobip media behavior.
- Always: store only transcript text and provider metadata already available.
- Always: leave unavailable customer fields empty.
- Ask first: external CRM sync, authentication, or cloud database migration.
- Never: expose API keys or invent customer information.

## Success Criteria

- A started call appears as active and becomes completed when its socket closes.
- Direction is `inbound` or `outbound`, with inbound as the safe default.
- Customer and AI transcript entries retain order and timestamps.
- Name, phone, address, need, and notes are extracted only from customer speech.
- Interest is classified only from customer speech as `needs_consultation`,
  `no_need`, or `unknown`.
- Dashboard filters direction, searches calls, and opens call details.
- Empty, loading, and error states are usable on desktop and mobile.
- Full automated suite and runtime smoke test pass.

## Assumptions

- SQLite is sufficient for this single-process deployment.
- Provider start payloads may contain `direction`, `from`, `to`, or custom
  parameters; missing values remain blank.
- Extraction is conservative and deterministic, avoiding a second AI request
  after each call.
