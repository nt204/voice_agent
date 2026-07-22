const state = {
  recordings: [],
  summary: { count: 0, total_bytes: 0 },
  selectedRecordingIds: new Set(),
};

const recordingList = document.querySelector("#recordingList");
const recordingSearch = document.querySelector("#recordingSearch");
const retentionDays = document.querySelector("#retentionDays");
const recordingStatus = document.querySelector("#recordingStatus");
const cleanupRecordingsButton = document.querySelector("#cleanupRecordingsButton");
const selectAllRecordings = document.querySelector("#selectAllRecordings");
const selectedRecordingCount = document.querySelector("#selectedRecordingCount");
const deleteSelectedRecordingsButton = document.querySelector("#deleteSelectedRecordingsButton");
const adminToken = new URLSearchParams(window.location.search).get("token") || "";

const escapeHtml = (value = "") => String(value).replace(
  /[&<>"']/g,
  char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]
);

function withAdminToken(url) {
  if (!adminToken) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(adminToken)}`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(withAdminToken(url), options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Không thể xử lý yêu cầu");
  }
  return data;
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function formatDate(value) {
  if (!value) return "Chưa có";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Thời gian không hợp lệ";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Ho_Chi_Minh",
    hour12: false,
  }).format(parsed);
}

function directionLabel(direction) {
  return direction === "outbound" ? "Gọi đi" : "Gọi đến";
}

function statusLabel(status) {
  return {
    active: "Đang ghi",
    completed: "Đã kết thúc",
    failed: "Ghi lỗi",
  }[status] || status || "Chưa rõ";
}

function primaryAudio(recording) {
  const files = recording.files || {};
  return files.mixed || files.inbound || files.outbound || null;
}

function retentionCutoff() {
  const days = Math.max(0, Number(retentionDays.value) || 0);
  return Date.now() - days * 24 * 60 * 60 * 1000;
}

function expiredRecordings() {
  const cutoff = retentionCutoff();
  return state.recordings.filter(recording => (
    recording.status !== "active"
    && recording.started_at
    && new Date(recording.started_at).getTime() < cutoff
  ));
}

function renderSummary() {
  document.querySelector("#recordingCount").textContent = state.summary.count || 0;
  document.querySelector("#recordingStorage").textContent = formatBytes(state.summary.total_bytes);
  document.querySelector("#expiredRecordingCount").textContent = expiredRecordings().length;
}

function searchableText(recording) {
  return [
    recording.id,
    recording.call_id,
    recording.phone,
    recording.to,
    recording.direction,
  ].join(" ").toLowerCase();
}

function recordingRow(recording) {
  const audio = primaryAudio(recording);
  const isActive = recording.status === "active";
  return `
    <article class="recording-row">
      <label class="recording-select-cell">
        <input class="recording-select-checkbox" data-recording-id="${escapeHtml(recording.id)}" type="checkbox"
          ${state.selectedRecordingIds.has(recording.id) ? "checked" : ""} ${isActive ? "disabled" : ""}>
        <span class="sr-only">Chọn bản ghi ${escapeHtml(recording.phone || recording.call_id || recording.id)}</span>
      </label>
      <div class="recording-identity">
        <strong>${escapeHtml(recording.phone || recording.call_id || recording.id)}</strong>
        <small>${escapeHtml(directionLabel(recording.direction))} · ${escapeHtml(recording.call_id || recording.id)}</small>
        <span class="recording-state ${escapeHtml(recording.status)}">${escapeHtml(statusLabel(recording.status))}</span>
      </div>
      <time datetime="${escapeHtml(recording.started_at)}">${escapeHtml(formatDate(recording.started_at))}</time>
      <div class="recording-audio">
        ${audio ? `<audio controls preload="metadata" src="${escapeHtml(withAdminToken(audio.url))}"></audio>` : "<span>Không có file audio</span>"}
      </div>
      <strong class="recording-size">${escapeHtml(formatBytes(recording.total_bytes))}</strong>
      <button class="recording-delete-button" data-recording-id="${escapeHtml(recording.id)}" type="button" ${isActive ? "disabled" : ""}>
        ${isActive ? "Đang ghi" : "Xóa"}
      </button>
    </article>`;
}

function filteredRecordings() {
  const term = recordingSearch.value.trim().toLowerCase();
  return state.recordings.filter(recording => !term || searchableText(recording).includes(term));
}

function reconcileSelectedRecordings() {
  const availableIds = new Set(
    state.recordings
      .filter(recording => recording.status !== "active")
      .map(recording => recording.id)
  );
  for (const recordingId of state.selectedRecordingIds) {
    if (!availableIds.has(recordingId)) state.selectedRecordingIds.delete(recordingId);
  }
}

function updateSelectionControls() {
  const selectable = filteredRecordings().filter(recording => recording.status !== "active");
  const selectedVisible = selectable.filter(recording => state.selectedRecordingIds.has(recording.id));
  const selectedCount = state.selectedRecordingIds.size;
  selectAllRecordings.disabled = selectable.length === 0;
  selectAllRecordings.checked = selectable.length > 0 && selectedVisible.length === selectable.length;
  selectAllRecordings.indeterminate = selectedVisible.length > 0 && selectedVisible.length < selectable.length;
  selectedRecordingCount.textContent = `Đã chọn ${selectedCount} bản ghi`;
  deleteSelectedRecordingsButton.textContent = selectedCount
    ? `Xóa đã chọn (${selectedCount})`
    : "Xóa đã chọn";
  deleteSelectedRecordingsButton.disabled = selectedCount === 0;
}

function renderRecordings() {
  const filtered = filteredRecordings();
  recordingList.innerHTML = filtered.length
    ? filtered.map(recordingRow).join("")
    : '<div class="recording-list-state">Không tìm thấy bản ghi phù hợp.</div>';
  updateSelectionControls();
}

async function loadRecordings({ announce = false } = {}) {
  try {
    const data = await requestJson("/admin/api/recordings");
    state.recordings = data.recordings || [];
    state.summary = data.summary || { count: 0, total_bytes: 0 };
    reconcileSelectedRecordings();
    renderSummary();
    renderRecordings();
    if (announce) {
      recordingStatus.textContent = "Đã cập nhật danh sách bản ghi.";
      recordingStatus.className = "form-status recording-page-status success";
    }
  } catch (error) {
    recordingList.innerHTML = `<div class="recording-list-state error">${escapeHtml(error.message)}</div>`;
    recordingStatus.textContent = error.message;
    recordingStatus.className = "form-status recording-page-status error";
  }
}

recordingList.addEventListener("click", async event => {
  const button = event.target.closest(".recording-delete-button");
  if (!button || button.disabled) return;
  const recordingId = button.dataset.recordingId;
  if (!window.confirm("Xóa file audio này? Lịch sử cuộc gọi và transcript vẫn được giữ lại.")) return;
  button.disabled = true;
  try {
    const result = await requestJson(`/admin/api/recordings/${encodeURIComponent(recordingId)}`, {
      method: "DELETE",
    });
    recordingStatus.textContent = `Đã xóa ${result.deleted_files} file, giải phóng ${formatBytes(result.freed_bytes)}.`;
    recordingStatus.className = "form-status recording-page-status success";
    state.selectedRecordingIds.delete(recordingId);
    await loadRecordings();
  } catch (error) {
    button.disabled = false;
    recordingStatus.textContent = error.message;
    recordingStatus.className = "form-status recording-page-status error";
  }
});

recordingList.addEventListener("change", event => {
  const checkbox = event.target.closest(".recording-select-checkbox");
  if (!checkbox || checkbox.disabled) return;
  const recordingId = checkbox.dataset.recordingId;
  if (checkbox.checked) state.selectedRecordingIds.add(recordingId);
  else state.selectedRecordingIds.delete(recordingId);
  updateSelectionControls();
});

selectAllRecordings.addEventListener("change", () => {
  for (const recording of filteredRecordings()) {
    if (recording.status === "active") continue;
    if (selectAllRecordings.checked) state.selectedRecordingIds.add(recording.id);
    else state.selectedRecordingIds.delete(recording.id);
  }
  renderRecordings();
});

deleteSelectedRecordingsButton.addEventListener("click", async () => {
  const recordingIds = [...state.selectedRecordingIds];
  if (!recordingIds.length) return;
  if (!window.confirm(`Xóa file audio của ${recordingIds.length} bản ghi đã chọn? Lịch sử cuộc gọi và transcript vẫn được giữ lại.`)) return;
  deleteSelectedRecordingsButton.disabled = true;
  try {
    const result = await requestJson("/admin/api/recordings/delete-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recording_ids: recordingIds }),
    });
    const skippedText = result.skipped_active
      ? ` Bỏ qua ${result.skipped_active} bản ghi đang hoạt động.`
      : "";
    recordingStatus.textContent = `Đã xóa ${result.deleted_recordings} bản ghi (${result.deleted_files} file), giải phóng ${formatBytes(result.freed_bytes)}.${skippedText}`;
    recordingStatus.className = "form-status recording-page-status success";
    state.selectedRecordingIds.clear();
    await loadRecordings();
  } catch (error) {
    recordingStatus.textContent = error.message;
    recordingStatus.className = "form-status recording-page-status error";
    updateSelectionControls();
  }
});

cleanupRecordingsButton.addEventListener("click", async () => {
  const days = Math.max(0, Math.min(3650, Number(retentionDays.value) || 0));
  retentionDays.value = String(days);
  const expiredCount = expiredRecordings().length;
  if (!expiredCount) {
    recordingStatus.textContent = `Không có bản ghi đã kết thúc nào cũ hơn ${days} ngày.`;
    recordingStatus.className = "form-status recording-page-status";
    return;
  }
  if (!window.confirm(`Xóa ${expiredCount} bản ghi đã kết thúc và cũ hơn ${days} ngày?`)) return;
  cleanupRecordingsButton.disabled = true;
  try {
    const result = await requestJson(`/admin/api/cleanup?days=${encodeURIComponent(days)}`, {
      method: "POST",
    });
    recordingStatus.textContent = `Đã dọn ${result.deleted_recordings} bản ghi, giải phóng ${formatBytes(result.freed_bytes)}.`;
    recordingStatus.className = "form-status recording-page-status success";
    await loadRecordings();
  } catch (error) {
    recordingStatus.textContent = error.message;
    recordingStatus.className = "form-status recording-page-status error";
  } finally {
    cleanupRecordingsButton.disabled = false;
  }
});

recordingSearch.addEventListener("input", renderRecordings);
retentionDays.addEventListener("input", renderSummary);
document.querySelector("#refreshRecordingsButton").addEventListener("click", () => loadRecordings({ announce: true }));

loadRecordings();
