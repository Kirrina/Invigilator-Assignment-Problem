import pulp
import os
import time
from data_preprocessing import preprocess_data, manual_data_adjustment, audit_static_feasibility
from model_builder import build_model
from solver import solve_model

def main():
    """
    Main orchestrator function.
    
    Steps:
    1. Load and validate input Excel file
    2. Preprocess data and extract parameters
    3. Interactive data adjustment menu
    4. Static Audit (Pre-solve check)
    5. Build ILP model
    6. Solve and export results
    
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

        # 3. Static Audit - Kiểm tra tiền khả thi
        print("\n[Step 3] Thực hiện Audit dữ liệu trước khi giải...")
        start_audit = time.time()
        is_feasible, audit_errors = audit_static_feasibility(data_model)
        audit_duration = time.time() - start_audit

        if not is_feasible:
            print("\n" + "-"*60)
            print("   KẾT QUẢ KIỂM TRA TIỀN KHẢ THI (PRE-SOLVE AUDIT)")
            print("-"*60)
            print(f"> STATUS: INFEASIBLE (Lỗi dữ liệu tĩnh)")
            print(f"> Thời gian kiểm tra: {audit_duration:.4f} giây")
            print(f"\nDanh sách các điểm nghẽn ({len(audit_errors)} lỗi):")
            for err in audit_errors[:10]:
                print(f"  [X] {err}")
            if len(audit_errors) > 10:
                print(f"  ... và {len(audit_errors) - 10} lỗi khác.")
            
            print("\n" + "!"*60)
            print("[-] CHƯƠNG TRÌNH DỪNG LẠI VÌ DỮ LIỆU KHÔNG THỂ GIẢI ĐƯỢC")
            print("    Vui lòng điều chỉnh file Excel hoặc Menu Adjustment (B_ij=0).")
            print("!"*60)
            return False
        
        # 4. Interactive Weight Tuning Loop
        weights = {
            'omega': 1.0, 'theta': 20.0,
            'TAX_LACK_STAFF': 10000.0, 'TAX_FORCE_BUSY': 5000.0, 'TAX_BAD_QUAL': 5000.0
        }
        
        # FIX: Thêm hàm validate weight
        def validate_weight(value, name, min_val=0, max_val=1000000):
            """Validate weight input với kiểm tra range"""
            try:
                val = float(value)
                if not (min_val <= val <= max_val):
                    print(f"❌ {name} phải trong khoảng [{min_val}, {max_val}]")
                    return None
                return val
            except ValueError:
                print(f"❌ Lỗi: Nhập số thực hợp lệ (VD: 15.5)")
                return None
        
        # FIX: Thêm tuning history tracking
        tuning_history = []
        
        while True:
            print("\n" + "="*60)
            print("   BƯỚC 4: GIẢI MÔ HÌNH VÀ TINH CHỈNH TRỌNG SỐ")
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
                print(f"   - Ép người bận nhẹ: {int(metrics['slack_busy'])} trường hợp (B_ij=1)")
                print(f"   - Sai chuyên môn:   {int(metrics['slack_qual'])} trường hợp")
                
                print(f"\n4. Chỉ số phụ (Penalty counts):")
                print(f"   - Số lần mệt mỏi:   {int(metrics['fatigue_count'])} ca")
                print(f"   - Số lần di chuyển/chờ: {int(metrics['travel_count'])} ca")
                print("-"*50)
                
                # FIX: Gợi ý cải thiện dựa trên lịch sử
                if len(tuning_history) > 0:
                    last = tuning_history[-1]
                    print("\n💡 GỢI Ý CẢI THIỆN:")
                    if metrics['gap'] and last.get('gap') and metrics['gap'] > last['gap']:
                        print(f"  ⚠️  Gap tăng từ {last['gap']} → {metrics['gap']} ca")
                        print(f"      Đề xuất: TĂNG theta (hiện {weights['theta']})")
                    if metrics['slack_cap'] > last.get('slack_cap', 0):
                        print(f"  ⚠️  Thiếu người tăng từ {last.get('slack_cap', 0)} → {int(metrics['slack_cap'])}")
                        print(f"      Đề xuất: GIẢM TAX_LACK_STAFF (hiện {weights['TAX_LACK_STAFF']})")
                    elif not tuning_history and status == 'Feasible':
                        print("  💡 Cách tốt hơn: Giảm TAX_* để cho phép more flexibility")
                
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
                    print("\n--- ĐIỀU CHỈNH THÔNG SỐ TRỌNG SỐ (WEIGHT TUNING) ---")
                    print("(Nhấn Enter để giữ nguyên giá trị cũ)")
                    print("\n📋 HƯỚNG DẪN:")
                    print("  - Nếu Gap lớn (không công bằng) → TĂNG theta")
                    print("  - Nếu Infeasible → GIẢM TAX_LACK_STAFF hoặc TAX_FORCE_BUSY")
                    print("  - theta, TAX_* phải > 0\n")
                    
                    # FIX: Thêm validation cho từng weight
                    tuning_success = True
                    
                    new_theta = weights['theta']
                    while True:
                        t = input(f" - Nhập theta mới ({weights['theta']}): ").strip()
                        if not t: break
                        validated = validate_weight(t, "theta", min_val=0, max_val=10000)
                        if validated:
                            new_theta = validated
                            break
                    
                    new_lack = weights['TAX_LACK_STAFF']
                    while True:
                        l = input(f" - Nhập TAX_LACK mới ({weights['TAX_LACK_STAFF']}): ").strip()
                        if not l: break
                        validated = validate_weight(l, "TAX_LACK_STAFF", min_val=0, max_val=1000000)
                        if validated:
                            new_lack = validated
                            break
                    
                    new_busy = weights['TAX_FORCE_BUSY']
                    while True:
                        b = input(f" - Nhập TAX_BUSY mới ({weights['TAX_FORCE_BUSY']}): ").strip()
                        if not b: break
                        validated = validate_weight(b, "TAX_FORCE_BUSY", min_val=0, max_val=1000000)
                        if validated:
                            new_busy = validated
                            break
                    
                    new_qual = weights['TAX_BAD_QUAL']
                    while True:
                        q = input(f" - Nhập TAX_QUAL mới ({weights['TAX_BAD_QUAL']}): ").strip()
                        if not q: break
                        validated = validate_weight(q, "TAX_BAD_QUAL", min_val=0, max_val=1000000)
                        if validated:
                            new_qual = validated
                            break
                    
                    # Update weights
                    weights['theta'] = new_theta
                    weights['TAX_LACK_STAFF'] = new_lack
                    weights['TAX_FORCE_BUSY'] = new_busy
                    weights['TAX_BAD_QUAL'] = new_qual
                    
                    # FIX: Lưu lịch sử tuning
                    tuning_history.append({
                        'iteration': len(tuning_history) + 1,
                        'weights': dict(weights),
                        'status': status,
                        'gap': metrics['gap'],
                        'slack_cap': metrics['slack_cap'],
                        'objective': metrics['obj_value']
                    })
                    
                    print("✓ Đã cập nhật cấu hình mới. Đang chuẩn bị giải lại...")
                else:
                    print(">>> Đã hủy bỏ.")
                    break
            else:
                print("\n" + "!"*60)
                print("[-] BÀI TOÁN VÔ NGHIỆM (INFEASIBLE)!")
                print("    Vui lòng xem phần Chẩn đoán (DIAGNOSIS) ở trên để biết chi tiết.")
                print("!"*60)
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
