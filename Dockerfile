# 1. Sử dụng Python image chính thức, bản rút gọn để nhẹ dung lượng
FROM python:3.9-slim

# 2. Cài đặt bộ giải CBC của Linux hệ điều hành
# Điều này cực kỳ quan trọng để code PuLP chạy ổn định trên Linux/Docker
RUN apt-get update && apt-get install -y \
    coinor-cbc \
    && rm -rf /var/lib/apt/lists/*

# 3. Thiết lập thư mục làm việc trong container
WORKDIR /app

# 4. Copy và cài đặt các thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy mã nguồn và dữ liệu vào container
COPY src/ ./src/
COPY input/ ./input/

# 6. Tạo thư mục output sẵn để lưu kết quả
RUN mkdir -p output

# 7. Lệnh khởi chạy chương trình (flag -u để in log liên tục ra console)
CMD ["python", "-u", "src/main.py"]
