# Spec: Tách trang quản lý sản phẩm và thanh điều hướng

## Objective

Tách trình chỉnh sửa sản phẩm khỏi bảng cuộc gọi thành trang `/admin/products`, đồng thời cung cấp thanh điều hướng chung để nhân viên chuyển nhanh giữa cuộc gọi, đơn hàng và sản phẩm. Giao diện dùng tên chức năng trực tiếp, không dùng các chữ trang trí như “AI”, “Trung tâm” hoặc “Danh mục kinh doanh”.

## Tech Stack

- FastAPI phục vụ hai trang HTML tĩnh.
- HTML, CSS và JavaScript thuần, không thêm dependency.
- API sản phẩm hiện có tại `/api/products` được giữ nguyên.

## Commands

- Kiểm thử: `python -m pytest tests/test_admin_navigation.py tests/test_dashboard_vietnamese.py tests/test_products.py -q`
- Dựng và chạy: `docker compose up -d --build`
- Kiểm tra trang: `Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/admin/products`

## Project Structure

- `app/static/index.html`: trang cuộc gọi và đơn hàng.
- `app/static/products.html`: trang quản lý sản phẩm riêng.
- `app/static/dashboard.js`: tương tác bảng cuộc gọi.
- `app/static/products.js`: tương tác quản lý sản phẩm.
- `app/static/dashboard.css`: hệ thống giao diện và thanh điều hướng chung.
- `tests/test_admin_navigation.py`: kiểm tra route, điều hướng và ranh giới giao diện.

## Code Style

```html
<nav class="app-nav" aria-label="Điều hướng chính">
  <a href="/admin">Cuộc gọi &amp; đơn hàng</a>
  <a class="active" href="/admin/products" aria-current="page">Sản phẩm</a>
</nav>
```

Tên hiển thị bằng tiếng Việt; ID trường dữ liệu và payload API giữ nguyên để không ảnh hưởng tích hợp.

## Testing Strategy

- Kiểm tra tĩnh rằng cả hai trang có thanh điều hướng và trạng thái active đúng.
- Kiểm tra `/admin/products` trả đúng tệp HTML.
- Kiểm tra trang chính không còn modal quản lý sản phẩm.
- Chạy lại các bài kiểm tra API sản phẩm và móc nối `product_id`.

## Boundaries

- Luôn giữ nguyên API, schema, ID trường form và cấu trúc lên đơn.
- Hỏi trước khi thay đổi nhà cung cấp thoại, dữ liệu sản phẩm hoặc cơ sở dữ liệu.
- Không thêm dependency, không xóa dữ liệu và không đổi giá sản phẩm.

## Success Criteria

- `/admin` và `/admin/products` chuyển qua lại bằng thanh điều hướng.
- Quản lý sản phẩm là trang độc lập, không còn cửa sổ phủ trên trang cuộc gọi.
- Không còn chữ “AI”, “Trung tâm” hoặc “Danh mục kinh doanh” trong nội dung giao diện quản trị.
- Thêm, sửa, đặt mặc định sản phẩm vẫn dùng các API hiện tại.
- Giao diện desktop và mobile không tràn ngang.

## Open Questions

Không có. Yêu cầu và ảnh mẫu đã xác định đủ phạm vi.
