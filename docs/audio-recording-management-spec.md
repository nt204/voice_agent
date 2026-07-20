# Spec: Quản lý và dọn dẹp bản ghi âm

## Objective

Thêm trang `/admin/recordings` để nhân viên quản trị biết hệ thống đang lưu bao nhiêu bản ghi, chiếm bao nhiêu dung lượng, nghe lại khi cần và xóa an toàn các bản ghi không còn cần thiết.

Phạm vi dữ liệu là các bản ghi do `CallRecorder` tạo trong thư mục cấu hình `CALL_RECORDINGS_DIR`. File lời chào trong `assets` không thuộc phạm vi quản lý.

Tiêu chí nghiệm thu:

- Thanh điều hướng có mục `Bản ghi âm`.
- Trang hiển thị tổng số bản ghi, tổng dung lượng, số bản ghi cũ hơn thời hạn đang chọn.
- Danh sách hiển thị số điện thoại, chiều gọi, thời gian, trạng thái, dung lượng và trình phát audio ưu tiên file `mixed`.
- Có tìm kiếm theo số điện thoại hoặc mã cuộc gọi.
- Có thể xóa một bản ghi sau khi xác nhận.
- Có thể dọn hàng loạt bản ghi đã kết thúc và cũ hơn N ngày sau khi xác nhận; mặc định N = 30.
- Không xóa bản ghi có trạng thái `active`, kể cả khi mốc thời gian đã quá hạn.
- Sau khi xóa, lịch sử cuộc gọi, transcript, phân tích và đơn hàng vẫn còn; phần bản ghi của cuộc gọi chuyển sang trạng thái không có file.
- API trả về số bản ghi, số file và số byte đã giải phóng để giao diện báo kết quả rõ ràng.

## Tech Stack

- FastAPI và Python cho API.
- SQLAlchemy và bảng `CallRecordingRow` hiện có cho metadata.
- HTML, CSS và JavaScript thuần theo cấu trúc các trang quản trị hiện tại.
- Pytest cho unit test và API test.

## Commands

- Chạy ứng dụng: `.\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 3000`
- Kiểm thử tính năng: `.\\.venv\\Scripts\\python.exe -m pytest tests\\test_recording_manager.py tests\\test_recordings_admin.py -q`
- Kiểm thử toàn bộ: `.\\.venv\\Scripts\\python.exe -m pytest -q`
- Kiểm tra Python: `.\\.venv\\Scripts\\python.exe -m compileall -q app`

## Project Structure

- `app/recording_manager.py`: liệt kê, tính dung lượng, xóa từng bản ghi và dọn theo thời hạn.
- `app/admin.py`: API quản lý bản ghi đang có; bổ sung validation và kết quả dung lượng giải phóng.
- `app/main.py`: route phục vụ trang `/admin/recordings`.
- `app/static/recordings.html`: giao diện quản lý bản ghi.
- `app/static/recordings.js`: tải dữ liệu, lọc, xác nhận và gọi API xóa.
- `app/static/dashboard.css`: dùng lại hệ thống style hiện tại, chỉ thêm style dành cho trang bản ghi.
- `tests/test_recording_manager.py`: hành vi xóa và bảo vệ bản ghi đang hoạt động.
- `tests/test_recordings_admin.py`: route/API và các hook giao diện.

## Code Style

Giữ hàm nhỏ, tên mô tả đúng kết quả và trả về thống kê có đơn vị rõ ràng:

```python
def cleanup_recordings(days: int) -> dict[str, int]:
    return {
        "deleted_recordings": deleted_recordings,
        "deleted_files": deleted_files,
        "freed_bytes": freed_bytes,
    }
```

JavaScript dùng `async/await`, kiểm tra `response.ok`, escape dữ liệu trước khi đưa vào HTML và hiển thị lỗi bằng vùng `role="status"`.

## Testing Strategy

- Unit test bằng thư mục tạm để chứng minh đúng file bị xóa và file ngoài recording root không bị tác động.
- Test cleanup chứng minh bản ghi `active` được giữ lại.
- API test chứng minh số ngày âm hoặc không hợp lệ bị từ chối.
- Static contract test chứng minh trang có điều hướng, xác nhận xóa, trình phát audio và gọi đúng endpoint.
- Không gọi Telnyx hoặc dịch vụ ngoài trong test.

## Boundaries

- Always: giới hạn path trong `CALL_RECORDINGS_DIR`, xác nhận trước thao tác xóa, giữ metadata lịch sử cuộc gọi ngoài bảng recording, bảo vệ bản ghi `active`.
- Ask first: tự động chạy cleanup theo lịch, đặt quota dung lượng cứng, chuyển audio sang object storage, thay đổi schema database.
- Never: xóa `assets`, xóa transcript/đơn hàng cùng audio, xóa file bằng path do trình duyệt gửi trực tiếp, tự động xóa bản ghi đang hoạt động.

## Success Criteria

- Người quản trị có thể tìm, nghe, xóa từng bản ghi và dọn bản ghi cũ từ giao diện.
- Dung lượng hiển thị cập nhật sau mỗi thao tác.
- Tất cả test tính năng mới chạy xanh.
- Không phát sinh dependency mới hoặc migration database.

## Open Questions

- Không còn câu hỏi chặn triển khai. Mặc định giữ bản ghi 30 ngày; tự động dọn theo lịch nằm ngoài phạm vi phiên bản này.
