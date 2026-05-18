import pulp
import os
from data_preprocessing import preprocess_data, manual_data_adjustment
from model_builder import build_model
from solver import solve_model

def main():
    # Lấy thư mục gốc của project để đường dẫn luôn đúng dù chạy từ đâu
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    file_excel = os.path.join(project_root, 'input', 'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx')
    
    # 1. Đọc và tiền xử lý dữ liệu (Mục 6)
    data_model = preprocess_data(file_excel)
    
    # 2. Điều chỉnh thủ công dữ liệu (Tuning dữ liệu giả lập)
    # Lưu ý: Bạn có thể nhập 0 để bỏ qua màn hình menu này và chạy ngay
    manual_data_adjustment(data_model)
    
    # 3. Khởi tạo mô hình ILP, biến và ràng buộc (Mục 7)
    prob, X = build_model(data_model)
    
    # 4. Giải bài toán
    solve_model(prob, X, data_model)

if __name__ == "__main__":
    main()