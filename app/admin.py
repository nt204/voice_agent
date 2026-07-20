from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

from app.config import config
from app.intent_extraction import extract_call_intent_for_recording
from app.recording_manager import (
    RecordingInUseError,
    cleanup_recordings,
    delete_recording,
    list_recordings,
    recording_path,
    storage_summary,
)
from app.reporting import export_sales_csv, sales_report
from app.telnyx_client import create_outbound_call


def _require_admin_token(request: Request) -> None:
    if not config.admin_token:
        return
    token = request.query_params.get("token") or request.headers.get("x-admin-token")
    if token != config.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


router = APIRouter(prefix="/admin", dependencies=[Depends(_require_admin_token)])


@router.get("", response_class=HTMLResponse)
async def admin_page() -> HTMLResponse:
    return HTMLResponse(_admin_html())


@router.get("/api/recordings")
async def api_recordings() -> dict:
    return {"summary": storage_summary(), "recordings": list_recordings()}


@router.get("/api/report")
async def api_report(days: int = 30) -> dict:
    return sales_report(days)


@router.get("/api/report.csv")
async def api_report_csv(days: int = 30) -> Response:
    return Response(
        content=export_sales_csv(days),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sales-report.csv"'},
    )


@router.post("/api/outbound-call")
async def api_outbound_call(payload: dict) -> dict:
    to_number = str(payload.get("to_number") or "").strip()
    from_number = str(payload.get("from_number") or "").strip() or None
    if not to_number:
        raise HTTPException(status_code=400, detail="Missing to_number")
    try:
        result = create_outbound_call(to_number, from_number)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Telnyx outbound call failed: {exc}") from exc
    return {"ok": True, "telnyx": result}


@router.delete("/api/recordings/{recording_id}")
async def api_delete_recording(recording_id: str) -> dict:
    try:
        result = delete_recording(recording_id)
    except RecordingInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result["deleted_recordings"] == 0:
        raise HTTPException(status_code=404, detail="Recording not found")
    return {"ok": True, **result}


@router.post("/api/recordings/{recording_id}/extract")
async def api_extract_recording(recording_id: str) -> dict:
    extracted = extract_call_intent_for_recording(recording_id)
    if extracted is None:
        raise HTTPException(status_code=404, detail="No transcript found for recording")
    return {"ok": True, "intent": extracted}


@router.post("/api/cleanup")
async def api_cleanup(days: int = Query(default=30, ge=0, le=3650)) -> dict:
    return {"ok": True, **cleanup_recordings(days)}


@router.get("/file/{recording_id}/{file_kind}")
async def admin_file(recording_id: str, file_kind: str):
    try:
        path = recording_path(recording_id, file_kind)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if file_kind == "log":
        return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))
    return FileResponse(path, media_type="audio/wav", filename=path.name)


def _admin_html() -> str:
    title = escape("Telnyx Call Manager")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #172026;
      --muted: #66737f;
      --line: #d9dee5;
      --accent: #0f766e;
      --danger: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 20px; font-weight: 650; }}
    main {{ padding: 20px 24px 32px; }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(180px, 1fr) auto auto auto;
      gap: 10px;
      align-items: center;
      margin-bottom: 16px;
    }}
    input, button {{
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      padding: 0 10px;
      font: inherit;
    }}
    button {{ cursor: pointer; }}
    button.primary {{ background: var(--accent); border-color: var(--accent); color: white; }}
    button.danger {{ color: var(--danger); }}
    .summary {{ color: var(--muted); white-space: nowrap; }}
    .outbound {{
      display: grid;
      grid-template-columns: minmax(180px, 1fr) minmax(180px, 1fr) auto;
      gap: 10px;
      margin-bottom: 16px;
      padding: 12px;
      background: var(--panel);
      border: 1px solid var(--line);
    }}
    .report {{
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      padding: 12px;
      min-height: 76px;
    }}
    .metric strong {{ display: block; font-size: 20px; margin-top: 4px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
    }}
    th, td {{
      padding: 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{ font-size: 12px; color: var(--muted); font-weight: 650; }}
    tr:last-child td {{ border-bottom: 0; }}
    audio {{ width: 220px; max-width: 100%; height: 32px; }}
    .muted {{ color: var(--muted); }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    dialog {{
      width: min(900px, calc(100vw - 32px));
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0;
    }}
    dialog::backdrop {{ background: rgba(15, 23, 42, .32); }}
    .dialog-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }}
    pre {{
      margin: 0;
      padding: 14px;
      max-height: 65vh;
      overflow: auto;
      white-space: pre-wrap;
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    @media (max-width: 900px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      .toolbar {{ grid-template-columns: 1fr 1fr; }}
      .report {{ grid-template-columns: 1fr 1fr; }}
      table, tbody, tr, td {{ display: block; }}
      thead {{ display: none; }}
      tr {{ border-bottom: 1px solid var(--line); padding: 10px; }}
      td {{ border: 0; padding: 6px 0; }}
      td::before {{ content: attr(data-label); display: block; color: var(--muted); font-size: 12px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Telnyx Call Manager</h1>
    <div class="summary" id="summary">Loading...</div>
  </header>
  <main>
    <div class="toolbar">
      <input id="search" type="search" placeholder="Search phone or time">
      <input id="days" type="number" min="0" value="14" aria-label="Cleanup days">
      <button class="primary" id="refresh">Refresh</button>
      <button class="danger" id="cleanup">Cleanup</button>
    </div>
    <div class="toolbar">
      <input id="reportDays" type="number" min="1" value="30" aria-label="Report days">
      <button class="primary" id="loadReport">Load Report</button>
      <button id="exportCsv">Export CSV</button>
      <span class="muted">Sales report window in days</span>
    </div>
    <div class="report" id="report"></div>
    <div class="outbound">
      <input id="outboundTo" type="tel" placeholder="Customer phone, e.g. +959..., +849..., VN 09...">
      <input id="outboundFrom" type="tel" placeholder="From number, optional">
      <button class="primary" id="callOut">Call Out</button>
    </div>
    <table>
      <thead>
        <tr>
          <th>Phone</th>
          <th>Time</th>
          <th>Status</th>
          <th>Intent</th>
          <th>Inbound</th>
          <th>Outbound</th>
          <th>Log</th>
          <th>Size</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </main>
  <dialog id="logDialog">
    <div class="dialog-head">
      <strong id="logTitle">Log</strong>
      <button id="closeLog">Close</button>
    </div>
    <pre id="logBody"></pre>
  </dialog>
  <script>
    let recordings = [];
    const adminToken = new URLSearchParams(window.location.search).get('token') || '';
    const tokenQuery = adminToken ? `?token=${{encodeURIComponent(adminToken)}}` : '';

    const rows = document.getElementById('rows');
    const search = document.getElementById('search');
    const summary = document.getElementById('summary');
    const dialog = document.getElementById('logDialog');
    const logBody = document.getElementById('logBody');
    const logTitle = document.getElementById('logTitle');

    async function load() {{
      const response = await fetch(`/admin/api/recordings${{tokenQuery}}`);
      const data = await response.json();
      recordings = data.recordings;
      summary.textContent = `${{data.summary.count}} calls · ${{data.summary.total_mb}} MB`;
      render();
    }}

    async function loadReport() {{
      const days = document.getElementById('reportDays').value || '30';
      const joiner = adminToken ? '&' : '?';
      const response = await fetch(`/admin/api/report${{tokenQuery}}${{joiner}}days=${{encodeURIComponent(days)}}`);
      const data = await response.json();
      document.getElementById('report').innerHTML = [
        metric('Total', data.total_calls),
        metric('Inbound', data.inbound_calls),
        metric('Outbound', data.outbound_calls),
        metric('Completed', data.completed_calls),
        metric('Order Intent', `${{data.order_intent_calls}} (${{data.order_intent_rate}}%)`),
        metric('Orders Complete', `${{data.order_complete_calls}} (${{data.conversion_rate}}%)`),
        metric('No Order', data.no_order_calls),
        metric('Active', data.active_calls),
        metric('Failed', data.failed_calls),
        metric('Minutes', data.total_minutes),
      ].join('');
    }}

    function metric(label, value) {{
      return `<div class="metric"><span class="muted">${{label}}</span><strong>${{escapeHtml(value)}}</strong></div>`;
    }}

    function render() {{
      const term = search.value.trim().toLowerCase();
      const filtered = recordings.filter(item => searchableText(item).includes(term));
      rows.innerHTML = filtered.map(rowHtml).join('') || '<tr><td colspan="9" class="muted">No recordings</td></tr>';
    }}

    function searchableText(item) {{
      const intent = item.intent || {{}};
      return [
        item.phone, item.to, item.timestamp, item.latest_time,
        intent.customer_name, intent.phone_number, intent.address,
        intent.product_name, intent.quantity, intent.combo
      ].filter(Boolean).join(' ').toLowerCase();
    }}

    function rowHtml(item) {{
      const inbound = item.files.inbound ? `<audio controls src="${{withToken(item.files.inbound.url)}}"></audio>` : '<span class="muted">Missing</span>';
      const outbound = item.files.outbound ? `<audio controls src="${{withToken(item.files.outbound.url)}}"></audio>` : '<span class="muted">Missing</span>';
      const log = item.files.log ? `<button data-log="${{withToken(item.files.log.url)}}" data-id="${{item.id}}">View</button>` : '<span class="muted">Missing</span>';
      const intent = intentHtml(item.intent || {{}});
      return `<tr>
        <td data-label="Phone">${{escapeHtml(item.phone)}}</td>
        <td data-label="Time">${{escapeHtml(item.timestamp || item.latest_time)}}</td>
        <td data-label="Status">${{escapeHtml(`${{item.direction || ''}} / ${{item.status || ''}} / ${{item.sales_status || ''}}`)}}</td>
        <td data-label="Intent">${{intent}}</td>
        <td data-label="Inbound">${{inbound}}</td>
        <td data-label="Outbound">${{outbound}}</td>
        <td data-label="Log">${{log}}</td>
        <td data-label="Size">${{formatBytes(item.total_bytes)}}</td>
        <td data-label="Actions"><div class="actions"><button data-extract="${{item.id}}">Extract</button><button class="danger" data-delete="${{item.id}}">Delete</button></div></td>
      </tr>`;
    }}

    function intentHtml(intent) {{
      const lines = [];
      if (intent.order_intent) lines.push('Order: yes');
      if (intent.customer_name) lines.push(`Name: ${{escapeHtml(intent.customer_name)}}`);
      if (intent.phone_number) lines.push(`Phone: ${{escapeHtml(intent.phone_number)}}`);
      if (intent.product_name) lines.push(`Product: ${{escapeHtml(intent.product_name)}}`);
      if (intent.quantity) lines.push(`Qty: ${{escapeHtml(intent.quantity)}}`);
      if (intent.combo) lines.push(`Combo: ${{escapeHtml(intent.combo)}}`);
      if (intent.address) lines.push(`Address: ${{escapeHtml(intent.address)}}`);
      if (intent.confidence) lines.push(`Conf: ${{Math.round(intent.confidence * 100)}}%`);
      return lines.length ? lines.join('<br>') : '<span class="muted">No clear intent</span>';
    }}

    function formatBytes(bytes) {{
      if (!bytes) return '0 B';
      if (bytes < 1024) return `${{bytes}} B`;
      if (bytes < 1024 * 1024) return `${{(bytes / 1024).toFixed(1)}} KB`;
      return `${{(bytes / 1024 / 1024).toFixed(1)}} MB`;
    }}

    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}

    function withToken(url) {{
      if (!adminToken) return url;
      return `${{url}}${{url.includes('?') ? '&' : '?'}}token=${{encodeURIComponent(adminToken)}}`;
    }}

    rows.addEventListener('click', async event => {{
      const logUrl = event.target.dataset.log;
      const deleteId = event.target.dataset.delete;
      const extractId = event.target.dataset.extract;
      if (logUrl) {{
        logTitle.textContent = event.target.dataset.id;
        logBody.textContent = await (await fetch(logUrl)).text();
        dialog.showModal();
      }}
      if (extractId) {{
        await fetch(`/admin/api/recordings/${{encodeURIComponent(extractId)}}/extract${{tokenQuery}}`, {{ method: 'POST' }});
        await load();
      }}
      if (deleteId && confirm(`Delete ${{deleteId}}?`)) {{
        await fetch(`/admin/api/recordings/${{encodeURIComponent(deleteId)}}${{tokenQuery}}`, {{ method: 'DELETE' }});
        await load();
      }}
    }});

    document.getElementById('refresh').addEventListener('click', load);
    document.getElementById('loadReport').addEventListener('click', loadReport);
    document.getElementById('exportCsv').addEventListener('click', () => {{
      const days = document.getElementById('reportDays').value || '30';
      const joiner = adminToken ? '&' : '?';
      window.location.href = `/admin/api/report.csv${{tokenQuery}}${{joiner}}days=${{encodeURIComponent(days)}}`;
    }});
    document.getElementById('cleanup').addEventListener('click', async () => {{
      const days = document.getElementById('days').value || '14';
      const joiner = adminToken ? '&' : '?';
      await fetch(`/admin/api/cleanup${{tokenQuery}}${{joiner}}days=${{encodeURIComponent(days)}}`, {{ method: 'POST' }});
      await load();
    }});
    document.getElementById('callOut').addEventListener('click', async () => {{
      const toNumber = document.getElementById('outboundTo').value.trim();
      const fromNumber = document.getElementById('outboundFrom').value.trim();
      if (!toNumber) {{
        alert('Enter customer phone number');
        return;
      }}
      const response = await fetch(`/admin/api/outbound-call${{tokenQuery}}`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{to_number: toNumber, from_number: fromNumber}})
      }});
      if (!response.ok) {{
        alert(await response.text());
        return;
      }}
      alert('Outbound call started');
    }});
    document.getElementById('closeLog').addEventListener('click', () => dialog.close());
    search.addEventListener('input', render);
    load();
    loadReport();
  </script>
</body>
</html>"""
