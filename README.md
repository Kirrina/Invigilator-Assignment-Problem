# IAP Solver - Hệ thống tối ưu hóa phân công giám thị (HCMUT)

Dự án này cung cấp bộ giải bài toán Phân công giám thị (Invigilator Assignment Problem - IAP) dựa trên mô hình Quy hoạch nguyên (Integer Linear Programming - ILP). Hệ thống sử dụng thư viện `PuLP` và bộ giải `CBC` để tìm ra phương án phân công tối ưu, cân bằng giữa tính công bằng và các ràng buộc thực tế.

## 🌟 Tính năng nổi bật

*   **Tối ưu hóa đa mục tiêu:** Cân bằng giữa độ lệch khối lượng công việc (Fairness) và các điểm phạt (Penalty) về di chuyển, mệt mỏi.
*   **Cơ chế Nới lỏng Ràng buộc (Slack Variables):** Đảm bảo hệ thống luôn tìm ra nghiệm ngay cả khi dữ liệu đầu vào có mâu thuẫn (Infeasible) thông qua chiến lược phạt Big-M.
*   **Tinh chỉnh trọng số tương tác (Interactive Tuning):** Cho phép người dùng đánh giá các chỉ số sức khỏe của lịch (Gap công bằng, số lần mệt mỏi, di chuyển...) và điều chỉnh trọng số (`theta`, `taxes`) ngay trong lúc chạy để có kết quả ưng ý nhất.
*   **Tối ưu hiệu năng vượt trội:** Sử dụng kỹ thuật tính toán trước (`X_sum`) giúp giảm thời gian xây dựng mô hình từ vài phút xuống còn vài giây, xử lý mượt mà hàng chục nghìn biến số.
*   **Xử lý thời gian thực:** Chống trùng lịch và kiểm tra di chuyển bất khả thi dựa trên giờ bắt đầu/kết thúc thực tế (Continuous-time logic).

## 🛠️ Yêu cầu hệ thống

*   **Python 3.8+**
*   Các thư viện bổ trợ: `pandas`, `numpy`, `pulp`, `openpyxl`.

Cài đặt nhanh bằng lệnh:
```bash
pip install -r requirements.txt
```
Hoặc:
## 🐳 Cách chạy chương trình qua Docker (Khuyên dùng)

Phương thức này đảm bảo chương trình chạy ổn định nhất vì bộ giải **CBC** và mọi thư viện đã được đóng gói sẵn trong môi trường ảo hóa.

### 1. Xây dựng Docker Image (Build)
Mở Terminal tại thư mục dự án và chạy lệnh:
```bash
docker build -t iap-solver .
```

### 2. Khởi chạy chương trình (Run)
Chương trình yêu cầu tương tác và cần xuất file ra máy thật, hãy chạy lệnh tương ứng với hệ điều hành:

*   **Trên Windows (PowerShell):**
    ```bash
    docker run -it -v ${PWD}/output:/app/output iap-solver
    ```
*   **Trên macOS/Linux:**
    ```bash
    docker run -it -v $(pwd)/output:/app/output iap-solver
    ```

**Lưu ý:** Tham số `-v` đảm bảo file Excel kết quả sinh ra bên trong Docker sẽ tự động xuất hiện tại thư mục `output/` trên máy tính của bạn.


## 🚀 Hướng dẫn sử dụng

1.  **Chuẩn bị dữ liệu:** Đặt file Excel dữ liệu vào thư mục `input/`. Đảm bảo file có các cột: *MS của CÁN BỘ COI THI, MS Ca thi, Ngày, GIỜ, Thời gian, Cơ sở, Nhiệm vụ*.
2.  **Chạy chương trình:**
    ```bash
    python src/main.py
    ```
3.  **Điều chỉnh dữ liệu (Tùy chọn):** Sau khi nạp dữ liệu, bạn có thể sửa trực tiếp Năng lực chuyên môn hoặc Lịch bận của cán bộ thông qua menu tương tác.
3.  **Tinh chỉnh và Xuất kết quả:** 
    *   Sau khi giải xong, máy sẽ in ra **Bảng chỉ số sức khỏe của lịch**.
    *   Nếu chưa ưng ý, chọn `2` để thay đổi trọng số Công bằng hoặc Thuế phạt.
    *   Nếu hài lòng, chọn `1` để xuất kết quả ra file `output/Optimized_Schedule.xlsx`.


## 📂 Cấu trúc mã nguồn


*   `src/main.py`: Bộ điều phối trung tâm và vòng lặp Tinh chỉnh (Tuning Loop).
*   `src/data_preprocessing.py`: Xử lý làm sạch dữ liệu, nội suy cơ sở và định danh ca thi duy nhất.
*   `src/model_builder.py`: Xây dựng mô hình toán học, biến quyết định và hệ phương trình ràng buộc.
*   `src/solver.py`: Thực thi bộ giải CBC (với `timeLimit=60s`) và trích xuất các chỉ số đánh giá.

---
**Nhóm phát triển - Mô hình hóa toán học (Nhóm 9 - L01)**
