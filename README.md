# Hướng dẫn chạy chương trình - Đề tài IAP (Invigilator Assignment Problem)

Chương trình này giải quyết bài toán Phân công giám thị sử dụng Quy hoạch nguyên (ILP) với thư viện PuLP, tuân thủ theo cấu trúc chia module chuyên nghiệp.

## 1. Yêu cầu hệ thống
* Máy tính cần cài đặt **Python 3.8+**.

## 2. Cài đặt thư viện
Mở Terminal/PowerShell tại thư mục gốc của project và chạy lệnh sau để cài đặt các thư viện cần thiết:
```bash
pip install -r requirements.txt
```

## 3. Cách chạy chương trình
Từ thư mục gốc của project, bạn khởi chạy chương trình bằng lệnh:
```bash
python src/main.py
```
*Lưu ý:* 
- Khi chạy, chương trình sẽ hiển thị một Menu Điều chỉnh (Data Adjustment) cho phép bạn cấu hình lại sở thích và năng lực của cán bộ. 
- Nhập `0` để bỏ qua menu và ngay lập tức chạy mô hình tối ưu (Solver). 
- Quá trình chạy có thể mất vài giây đến vài phút tùy cấu hình máy.

## 4. Cấu trúc thư mục dự án
Chương trình được thiết kế theo chuẩn module hóa, chia tách rõ ràng giữa Dữ liệu và Source Code:

```text
IAP/
├── input/
│   └── Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx  <-- Đặt file dữ liệu gốc (Baseline) vào đây
├── output/
│   └── Optimized_Schedule.xlsx                                 <-- File Excel kết quả tối ưu sẽ tự động xuất ra đây
├── src/
│   ├── main.py                 <-- File chạy chính (Orchestrator)
│   ├── data_preprocessing.py   <-- Module đọc Excel, sinh dữ liệu giả lập (L_i, Sở thích...)
│   ├── model_builder.py        <-- Module chứa các công thức ILP (Biến x_ijr, Ràng buộc cứng, Điểm phạt)
│   └── solver.py               <-- Module thực thi gọi PuLP CBC Solver và xuất báo cáo
├── requirements.txt            <-- File chứa danh sách thư viện
└── README.md                   <-- File hướng dẫn sử dụng
```
