import pulp
import os
from data_preprocessing import preprocess_data, manual_data_adjustment
from model_builder import build_model
from solver import solve_model

def main():
    """
    Main orchestrator function.
    
    Steps:
    1. Load and validate input Excel file
    2. Preprocess data and extract parameters
    3. Interactive data adjustment menu
    4. Build ILP model
    5. Solve and export results
    
    Returns:
        bool: True if successful, False if failed
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    file_excel = os.path.join(project_root, 'input', 'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx')
    
    # Validate file exists
    if not os.path.exists(file_excel):
        print("=" * 60)
        print("❌ ERROR: Input file not found!")
        print("=" * 60)
        print(f"\nExpected location: {file_excel}")
        print(f"\nPlease ensure:")
        print("  1. Create an 'input' folder in the project root")
        print("  2. Place the Excel file in that folder")
        print("  3. File must be named: 'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx'")
        print("\nCurrent working directory:", os.getcwd())
        print("Project root:", project_root)
        return False
    
    try:
        # 1. Read and preprocess data
        print("\n[Step 1] Loading and validating Excel file...")
        data_model = preprocess_data(file_excel)
        
        # 2. Interactive data adjustment
        print("\n[Step 2] Data adjustment menu...")
        manual_data_adjustment(data_model)
        
        # 3. Interactive Weight Tuning Loop
        weights = {
            'omega': 1.0, 'theta': 20.0,
            'TAX_LACK_STAFF': 10000.0, 'TAX_FORCE_BUSY': 5000.0, 'TAX_BAD_QUAL': 5000.0
        }
        
        while True:
            print("\n" + "="*60)
            print("   BƯỚC 3: GIẢI MÔ HÌNH VÀ TINH CHỈNH TRỌNG SỐ")
            print("="*60)
            print(f"> Cấu hình hiện tại: Công bằng (theta)={weights['theta']}, Phạt ép người bận={weights['TAX_FORCE_BUSY']}")
            
            prob, X = build_model(data_model, weights=weights)
            status, metrics = solve_model(prob, X, data_model, skip_export=True)
            
            if status in ['Optimal', 'Near-Optimal', 'Feasible']:
                print("\n" + "-"*50)
                print("   CHỈ SỐ SỨC KHỎE CỦA LỊCH PHÂN CÔNG")
                print("-"*50)
                if status == 'Optimal':
                    print(">>> STATUS: Global Optimal Solution found.")
                elif status == 'Near-Optimal':
                    print(">>> STATUS: Solver terminated at relative optimality gap (Target 2%).")
                    print("    The obtained solution is considered near-optimal.")
                else: # Feasible
                    print(">>> STATUS: Solver reached time limit (60s).")
                    print("    The obtained solution is feasible, but quality is unproven (Gap > 2%).")
                
                print(f"\n1. Thông số hiệu năng (Solver Metrics):")
                print(f"   - Objective Value: {metrics['obj_value']:.2f}")
                print(f"   - Solve Time:      {metrics['solve_time']:.2f} seconds")
                
                print(f"\n2. Độ lệch công bằng (Gap): {metrics['gap']} ca")
                print(f"   (Max: {metrics['high']} | Min: {metrics['low']})")
                
                print(f"\n3. Vi phạm ràng buộc mềm (Soft Constraint Violations):")
                print(f"   - Thiếu người gác:  {int(metrics['slack_cap'])} vị trí")
                print(f"   - Ép người bận:     {int(metrics['slack_busy'])} trường hợp")
                print(f"   - Sai chuyên môn:   {int(metrics['slack_qual'])} trường hợp")
                
                print(f"\n4. Chỉ số phụ (Penalty counts):")
                print(f"   - Số lần mệt mỏi:   {int(metrics['fatigue_count'])} ca")
                print(f"   - Số lần di chuyển/chờ: {int(metrics['travel_count'])} ca")
                print("-"*50)
                
                print("\nLỰA CHỌN CỦA BẠN:")
                print("1. Chấp nhận và Xuất file Excel")
                print("2. Thay đổi trọng số (Tuning) và Giải lại")
                print("0. Hủy bỏ và Thoát")
                
                choice = input("Nhập lựa chọn (0-2): ").strip()
                
                if choice == '1':
                    from solver import export_to_excel
                    export_to_excel(prob, X, data_model)
                    break
                elif choice == '2':
                    print("\n--- ĐIỀU CHỈNH THÔNG SỐ ---")
                    try:
                        t = input(f"Nhập theta mới (Hiện tại {weights['theta']}, tăng để lịch đều hơn): ").strip()
                        if t: weights['theta'] = float(t)
                        
                        b = input(f"Nhập Tax_Busy mới (Hiện tại {weights['TAX_FORCE_BUSY']}, tăng để giảm ép bận): ").strip()
                        if b: weights['TAX_FORCE_BUSY'] = float(b)
                    except ValueError:
                        print("❌ Giá trị không hợp lệ. Vui lòng nhập số.")
                else:
                    print(">>> Đã hủy bỏ.")
                    break
            else:
                print("\n" + "!"*60)
                print("[-] KHÔNG TÌM THẤY LỜI GIẢI KHẢ THI (INFEASIBLE)!")
                print("!"*60)
                print("\nLÝ DO TOÁN HỌC:")
                print("Không gian nghiệm rỗng. Các ràng buộc cứng đang mâu thuẫn lẫn nhau.")
                print("Việc thay đổi trọng số (Penalty weights) sẽ KHÔNG giải quyết được lỗi này.")
                
                print("\nCÁC NGUYÊN NHÂN CÓ THỂ GÂY LỖI:")
                print("1. Thiếu hụt nhân sự: Số lượng cán bộ (CB) ít hơn nhu cầu tối thiểu tại các ca cao điểm.")
                print("2. Mâu thuẫn di chuyển: Quá nhiều ca thi sát giờ (< 2 tiếng) ở các cơ sở khác nhau.")
                print("3. Cấu hình bận (B_ij): Quá nhiều cán bộ bị đánh dấu bận, không còn ai đủ điều kiện.")
                
                print("\nHƯỚNG GIẢI QUYẾT:")
                print("A. Kiểm tra file Excel: Tăng số lượng cán bộ hoặc giảm bớt yêu cầu tại ca thi.")
                print("B. Kiểm tra Menu Adjustment: Mở khóa trạng thái bận (B_ij=0) cho một số cán bộ.")
                print("C. Kiểm tra logic Travel: Xem lại các ca thi ở CS1 và CS2 có quá gần nhau không.")
                
                print("\n>>> Chương trình dừng tại đây để bảo vệ tính chính xác của dữ liệu.")
                return False
        
        return True
    
    except FileNotFoundError as e:
        print(f"\n❌ FILE ERROR: {e}")
        return False
    except ValueError as e:
        print(f"\n❌ DATA VALIDATION ERROR: {e}")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("   IAP - INVIGILATOR ASSIGNMENT PROBLEM SOLVER")
    print("="*60)
    
    success = main()
    
    if success:
        print("\n" + "="*60)
        print("✓ Program completed successfully!")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print("✗ Program failed - please check the errors above")
        print("="*60 + "\n")
