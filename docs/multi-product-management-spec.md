# Spec: Multi-product voice sales management

## Objective

Add product management to the existing Voice AI Sales application so one deployment can operate multiple products. Each product has its own Telnyx number, greetings, sales instructions, knowledge, and offers. Inbound calls select the product by the called number. Outbound calls require an explicit product selection.

The existing Venus BigOne call and order behavior remains the compatibility baseline. The feature must not change the order response shape, delivery-field workflow, confirmation rules, statuses, or missing-field semantics.

## Tech Stack

- Python 3, FastAPI, SQLAlchemy, PostgreSQL in Docker, SQLite in local tests
- Gemini Live for the call conversation and Gemini extraction for final call analysis
- Telnyx TeXML and bidirectional WebSocket audio
- Native HTML, CSS, and JavaScript for the admin dashboard
- pytest for unit and integration coverage

## Commands

- Run focused tests: `python -m pytest tests/test_products.py tests/test_call_history.py tests/test_prompts.py -q`
- Run all tests: `python -m pytest -q`
- Start the application: `docker compose up --build`
- Check health: `curl.exe http://127.0.0.1:3000/health`
- Open dashboard: `http://127.0.0.1:3000/admin`

## Project Structure

- `app/products.py`: product validation and product-specific prompt composition
- `app/call_history.py`: shared SQLAlchemy table definitions and compatibility summaries
- `app/sql_call_history.py`: product CRUD, product filtering, and call/order association
- `app/main.py`: product APIs, Telnyx product routing, and outbound product selection
- `app/static/index.html`: product selector and product-management drawer markup
- `app/static/dashboard.js`: product CRUD, filtering, and outbound selection behavior
- `app/static/dashboard.css`: responsive product-management UI
- `tests/test_products.py`: product persistence, routing, APIs, and compatibility tests
- `docs/multi-product-management-spec.md`: this specification

## Code Style

Use small typed helpers and validate input at the API boundary. Preserve existing response fields and add product data without renaming old fields.

```python
product = call_history.get_product(product_id)
if not product or not product["active"]:
    raise HTTPException(status_code=400, detail="Select an active product")
```

Frontend controls use labels above inputs, inline error messages, keyboard-accessible dialogs, one blue accent, 8px radii, and no decorative animation.

## Data Model

### products

- `id`: integer primary key
- `name`: required display name
- `slug`: unique stable identifier
- `phone_number`: unique normalized Telnyx number
- `texml_app_id`: optional product-specific Telnyx TeXML application
- `inbound_greeting`: required product greeting
- `outbound_greeting`: required product greeting
- `system_prompt`: product-specific sales behavior
- `knowledge`: product facts and restrictions
- `language_code`: defaults to `my-MM`
- `voice_name`: defaults to `Aoede`
- `active`: controls selection and inbound routing
- timestamps

### product_offers

- `id`, `product_id`, `name`, `quantity`, `unit_price`, `total_price`, `shipping_policy`, `active`

### Existing records

- Add nullable `product_id` to `calls`, `orders`, and `outbound_call_requests`.
- Keep all existing order columns and values unchanged.
- Seed one default Venus BigOne product from the current configuration and `product.md` when the product table is empty.
- Historical records may remain unassigned. No guessing or destructive backfill.

## Call Routing

### Inbound

1. Read the called number from the Telnyx answer webhook.
2. Resolve an active product by `phone_number`.
3. Put `product_id` into the WebSocket stream URL.
4. Load only that product's prompt, knowledge, greeting, voice, and language for the Gemini session.
5. Persist `product_id` on the call and resulting order.

If no product matches, use the default active product for backward compatibility.

### Outbound

1. Dashboard sends `product_id` and `to_number`.
2. API rejects missing or inactive products when more than one product exists.
3. Use the selected product's `phone_number` as `From` and optional `texml_app_id` for Telnyx.
4. Add `product_id` to answer, status, and WebSocket URLs.
5. Persist product association before callbacks arrive.

## Order Compatibility Contract

- Do not rename, remove, or reinterpret existing order response fields.
- Do not change delivery-state collection or confirmation behavior.
- Do not change existing intent and order status enums.
- Product knowledge may vary by call, but extraction output remains the existing schema.
- Product offers are authoritative for the selected product only.
- The existing Venus BigOne regression expectations remain unchanged.
- A product edit affects future calls only. Existing order snapshots keep their recorded product name and prices.

## Testing Strategy

- Unit tests for product validation and prompt isolation.
- SQLite integration tests for CRUD, unique phone numbers, active/default behavior, filters, and associations.
- FastAPI route tests for product APIs and outbound validation without calling Telnyx.
- Regression tests that assert existing Venus order fields and confirmation behavior remain unchanged.
- Static dashboard tests for product selectors, dialog accessibility, loading, empty, and error states.
- Full pytest suite after focused tests pass.
- Manual browser check at desktop and mobile widths against a locally running app.

## Boundaries

- Always: preserve existing API fields; normalize phone numbers; parameterize SQL; escape user content in the dashboard; retain order snapshots; run full tests.
- Ask first: change order field names, confirmation workflow, intent/status enums, Telnyx credentials, or public deployment configuration.
- Never: store API secrets in product rows; combine all products into one Gemini prompt; delete historical calls; silently assign historical records to a product; expose raw product content without HTML escaping.

## Success Criteria

- Admin can create, edit, activate, and deactivate products and offers without editing `.env` or restarting the app.
- Quick Call requires or auto-selects a valid active product and uses its Telnyx number.
- An inbound call uses the product mapped to the called number.
- Calls and orders display and filter by product.
- Gemini receives only the selected product's information.
- Venus BigOne order structure and existing order tests remain unchanged.
- Product screens provide clear loading, empty, validation, success, and error states.
- Dashboard remains usable on desktop, tablet, and mobile.
- All tests pass and the live local dashboard loads without console errors.

## Open Questions

- Product-specific Telnyx credentials are intentionally out of scope. The deployment continues to use one account API key, with product-specific numbers and optional TeXML application IDs.
- Import/export of products is deferred until normal CRUD usage proves it is needed.
