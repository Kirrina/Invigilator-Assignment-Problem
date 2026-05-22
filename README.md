# IAP Solver - Hệ thống tối ưu hóa phân công giám thị (HCMUT)

Dự án này cung cấp bộ giải bài toán Phân công giám thị (Invigilator Assignment Problem - IAP) dựa trên mô hình Quy hoạch nguyên (Integer Linear Programming - ILP). Hệ thống sử dụng thư viện `PuLP` và bộ giải `CBC` để tìm ra phương án phân công tối ưu, cân bằng giữa tính công bằng và các ràng buộc thực tế.

## 🌟 Tính năng nổi bật

*   **Tối ưu hóa đa mục tiêu:** Cân bằng giữa độ lệch khối lượng công việc (Fairness) và các điểm phạt (Penalty) về di chuyển, mệt mỏi.
*   **Cơ chế Nới lỏng Ràng buộc (Slack Variables):** Đảm bảo hệ thống luôn tìm ra nghiệm ngay cả khi dữ liệu đầu vào có mâu thuẫn (Infeasible) thông qua chiến lược phạt Big-M.
*   **Hệ thống Cache thông minh:** Tự động lưu trữ và tái sử dụng trạng thái bận ($B_{ij}$) và sở thích cơ sở ($Campus\_like$) giúp kết quả thực nghiệm ổn định và so sánh baseline chính xác.
*   **Tinh chỉnh trọng số tương tác (Interactive Tuning):** Cho phép người dùng đánh giá các chỉ số sức khỏe của lịch và điều chỉnh trọng số ngay trong lúc chạy.
*   **Phân tích hiệu năng chuyên sâu:** Bộ công cụ so sánh lịch Solver với lịch Baseline thực tế, đo lường mức độ cải thiện tính công bằng và chất lượng phân công.

## 🛠️ Yêu cầu hệ thống

*   **Python 3.8+**
*   Các thư viện bổ trợ: `pandas`, `numpy`, `pulp`, `openpyxl`, `matplotlib`.

Cài đặt nhanh bằng lệnh:
```bash
pip install -r requirements.txt
```

## 🚀 Hướng dẫn sử dụng chi tiết

### 1. Chuẩn bị dữ liệu
Đặt file Excel dữ liệu vào thư mục `input/`. Đảm bảo file có tên `Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx` với đầy đủ các cột thông tin ca thi và cán bộ.

### 2. Chạy chương trình
```bash
python src/main.py
```

### 3. Điều chỉnh dữ liệu (Data Adjustment)
Trước khi giải, hệ thống cung cấp Menu tương tác để bạn hiệu chỉnh dữ liệu đầu vào:
*   **Lựa chọn 1 (Xem thông tin):** Kiểm tra năng lực hiện tại, sở thích cơ sở và số lượng ca bận của một cán bộ cụ thể.
*   **Lựa chọn 2 (Năng lực chuyên môn):** Cập nhật trình độ cho cán bộ (1: CBCT, 2: Thư ký, 3: Trưởng HĐ).
*   **Lựa chọn 3 (Sở thích cơ sở):** Thay đổi mức độ ưu tiên làm việc tại các cơ sở (1: Ghét, 2: Bình thường, 3: Thích).
*   **Lựa chọn 4 (Trạng thái bận):** Đặt trạng thái bận cho cặp (Cán bộ, Ca thi). Có 3 mức:
    *   `0`: Rảnh (Sẵn sàng làm).
    *   `1`: Bận nhẹ (Có thể bị ép đi làm kèm điểm phạt).
    *   `2`: Bận tuyệt đối (Hệ thống tuyệt đối không phân công).

### 4. Kiểm tra tiền khả thi (Static Audit)
Sau khi nhấn `0` để thoát Menu Adjustment, hệ thống sẽ tự động thực hiện **Audit**. Nếu phát hiện thiếu người trầm trọng hoặc không đủ cán bộ đạt trình độ cho một ca thi, chương trình sẽ cảnh báo và yêu cầu bạn điều chỉnh lại dữ liệu trước khi giải để tránh lãng phí thời gian tính toán.

### 5. Tinh chỉnh tham số (Weight Tuning)
Sau khi Solver tìm ra lời giải, bạn sẽ nhận được **Chỉ số sức khỏe của lịch**. Nếu chưa ưng ý, hãy chọn `2` để tinh chỉnh tham số:
*   **theta ($\theta$):** Tăng giá trị này nếu bạn muốn lịch **công bằng hơn** (giảm Gap giữa người làm nhiều nhất và ít nhất).
*   **TAX_LACK_STAFF:** Tăng nếu muốn **giảm số vị trí bị thiếu** (ép hệ thống tìm người bằng mọi giá).
*   **TAX_FORCE_BUSY:** Tăng để hạn chế tối đa việc **ép người bận đi làm**.
*   **TAX_BAD_QUAL:** Tăng để hạn chế việc **phân công sai chuyên môn** (vượt cấp).

### 6. Xuất kết quả
Khi các chỉ số đã đạt yêu cầu, chọn `1` để xuất kết quả ra file `output/Optimized_Schedule.xlsx`.

## 📂 Cấu trúc mã nguồn

```text
IAP_PROJECT/
├── input/               # Chứa file Excel đầu vào
├── output/              # Kết quả lịch tối ưu và các file Cache
│   ├── B_ij_cache.json        # Lưu trữ trạng thái bận
│   ├── Campus_like_cache.json # Lưu trữ sở thích cơ sở
│   └── solver_metrics.json    # Chỉ số đánh giá sau khi giải
├── src/                 # Mã nguồn chính
│   ├── main.py                # Bộ điều phối trung tâm & Tuning Loop
│   ├── data_preprocessing.py   # Làm sạch, Cache & Cắt dữ liệu
│   ├── model_builder.py        # Xây dựng mô hình ILP & Biến Slack
│   ├── solver.py               # Thực thi bộ giải & Trích xuất metrics
│   ├── analysis.py             # Phân tích đối sánh Baseline vs Solver
│   ├── busy_rate_experiment.py # Thực nghiệm ngưỡng chịu tải
│   └── evaluate_time.py        # Đo lường hiệu năng theo quy mô
├── requirements.txt     # Danh sách thư viện cần thiết
└── README.md            # Hướng dẫn sử dụng
```

## 📊 Công cụ Phân tích & Thực nghiệm

Dự án tích hợp các công cụ chuyên sâu dành cho nghiên cứu:
*   **`src/analysis.py`**: Chạy sau khi có kết quả Solver để so sánh chi tiết với lịch phân công gốc trong file Excel.
*   **`src/busy_rate_experiment.py`**: Tự động chạy nhiều kịch bản với tỉ lệ bận khác nhau để tìm ngưỡng "tới hạn" của hệ thống.
*   **`src/evaluate_time.py`**: Đo lường tốc độ xử lý của mô hình theo quy mô dữ liệu (Subset).

---
**Nhóm phát triển - Mô hình hóa toán học (Nhóm 9 - L01)**
