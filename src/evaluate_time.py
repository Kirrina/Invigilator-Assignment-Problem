# file: benchmark.py
import time
import pulp
from data_preprocessing import preprocess_data, slice_data_model
from model_builder import build_model
import os  # Nhớ import os ở đầu file nếu chưa có

DEFAULT_WEIGHTS = {
    'omega': 1.0, 'theta': 20.0,
    'TAX_LACK_STAFF': 10000.0, 'TAX_FORCE_BUSY': 5000.0, 'TAX_BAD_QUAL': 5000.0
}
def run_time_experiment(cb_size, ct_size):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    file_excel = os.path.join(project_root, 'input', 'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx')
    print(f"\n[EXPERIMENT] Đang chạy thí nghiệm với Subset CB={cb_size}, CT={ct_size}...")
    
    # 1. Load và cắt dữ liệu mẫu
  
    data_model = preprocess_data(file_excel)
    sub = slice_data_model(data_model, cb_size, ct_size)
    
    # 2. Xây dựng mô hình toán
    prob, X = build_model(sub, weights=DEFAULT_WEIGHTS)
    
    # 3. Bắt đầu bấm giờ đo thời gian thực thi cốt lõi của Solver
    t0 = time.perf_counter()
    status = prob.solve(pulp.PULP_CBC_CMD(msg=True, timeLimit=30)) # Tắt log để giao diện sạch
    elapsed = time.perf_counter() - t0
    
    return elapsed

if __name__ == "__main__":
    # Cấu hình chạy thử với các kích thước subset khác nhau tại đây để làm biểu đồ
    run_time_experiment(cb_size=15, ct_size=17)