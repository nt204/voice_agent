# Spec: Separate Dialed Phone and Customer-Provided Phone

## Objective

Store and display the telephony routing number separately from the phone number
spoken or entered by the customer for delivery. The outbound destination must
never be overwritten by post-call extraction, and an order must use only the
customer-provided phone when the customer attempted to provide one.

Acceptance behavior:

- Outbound calls retain the original destination as `dialed_phone`.
- Transcript or confirmed DTMF extraction writes `customer_phone` only.
- Order `customer_phone` is sourced from the customer-provided value, not the
  outbound destination, when the customer attempts to provide a number.
- The call API returns both values independently.
- The dashboard labels and displays both values without ambiguity.
- Existing call data remains readable after migration.

## Tech Stack

- Python 3.12, FastAPI
- SQLite and PostgreSQL/SQLAlchemy call-history implementations
- Static HTML/CSS/JavaScript dashboard
- Pytest

## Commands

- Focused tests: `python -m pytest tests/test_call_history.py -q`
- Related tests: `python -m pytest tests/test_call_history.py tests/test_order_extraction.py tests/test_myanmar_call_scenarios.py -q`
- Full tests: `python -m pytest -q`
- Deploy: `docker compose up -d --build app`
- Runtime check: `docker compose exec -T app python -c "from app.main import call_history; print(call_history.list_calls(limit=1))"`

## Project Structure

- `app/call_history.py`: SQLite schema, migration, persistence and API shapes
- `app/sql_call_history.py`: PostgreSQL persistence and API shapes
- `app/main.py`: inbound/outbound provider routing and call initialization
- `app/static/index.html`: call list and call-detail presentation
- `tests/test_call_history.py`: persistence and compatibility coverage
- `tests/test_order_extraction.py`: customer-provided phone selection coverage

## Code Style

Use explicit domain names rather than generic `phone` variables at persistence
boundaries:

```python
store.start_call(
    call_id=call_id,
    direction="outbound",
    provider="telnyx",
    dialed_phone=to_phone,
)
```

API output should keep both meanings visible:

```json
{
  "dialed_phone": "+959793905153",
  "customer": {"phone": "0999809974"}
}
```

## Testing Strategy

- Start with a failing persistence test proving that finishing a call does not
  overwrite `dialed_phone` when a different customer number is extracted.
- Cover SQLite and PostgreSQL-compatible schema behavior through the existing
  store tests where practical.
- Assert the serialized call detail exposes both values.
- Run the order extraction regression suite to ensure metadata fallback remains
  safe and customer-provided digits still win.
- Verify the rebuilt container against the active PostgreSQL database and public
  API.

## Boundaries

- Always: preserve the original telephony number, migrate additively, and keep
  historical rows readable.
- Ask first: renaming or deleting existing API fields, dropping columns, or
  rewriting historical customer-provided phone values.
- Never: use an outbound destination as a confirmed delivery number after the
  customer attempted to provide a different number; expose credentials; delete
  existing calls or orders as part of migration.

## Success Criteria

1. A call started to `+959793905153` and completed with spoken phone
   `0999809974` returns both values unchanged in call detail.
2. Its order uses `0999809974`.
3. Calls without a spoken/confirmed phone keep `customer.phone` empty while
   retaining `dialed_phone`.
4. Dashboard call detail shows separate labels for the two phone values.
5. Existing databases migrate without destructive changes.
6. Focused and related tests pass, and the running Docker/API path is verified.

## Open Questions

- Assumption: for inbound calls, the source caller ID is retained as the routing
  phone but is not automatically considered a customer-confirmed delivery phone
  after the customer attempts to provide another value.
- Assumption: the existing `customer.phone` API shape remains the
  customer-provided/delivery number for compatibility; `dialed_phone` is added at
  the call level.
