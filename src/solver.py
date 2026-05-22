import pulp
import pandas as pd
import os
import time
from data_preprocessing import audit_static_feasibility

def solve_model(prob, X, data_model, skip_export=False):
    """Giải mô hình và trả về các chỉ số đánh giá chi tiết"""
    print("\n" + "-"*60)
    print("--- Bắt đầu chạy Solver (PuLP - CBC) ---")
    print(f"Cấu hình: TimeLimit=60s, Optimality Gap=2% (0.02)")
    print("-"*60)

    # Bắt đầu đo thời gian và giải
    start_time = time.time()
    
    # gapRel=0.02: Dừng nếu đạt sai số 2% so với tối ưu tuyệt đối
    # msg=True: Hiển thị log của CBC để theo dõi Gap
    status = prob.solve(pulp.PULP_CBC_CMD(msg=True, timeLimit=60, gapRel=0.02))
    
    solve_duration = time.time() - start_time
    status_raw = pulp.LpStatus[status]
    obj_val = pulp.value(prob.objective)

    # 1. Tính toán Gap thực tế trước (Skeptical approach)
    actual_gap = None
    best_bound = None
    if obj_val is not None and obj_val != 0:
        # Thử lấy bestBound từ nhiều nguồn của PuLP
        try:
            best_bound = prob.bestBound
            if best_bound is None and hasattr(prob, 'solver'):
                best_bound = getattr(prob.solver, 'bestBound', None)
        except Exception:
            pass
            
        if best_bound is not None:
            actual_gap = abs(obj_val - best_bound) / abs(obj_val)

    # 2. Phân loại trạng thái (Khắt khe hơn)
    if status_raw == 'Infeasible':
        final_status = 'Infeasible'
    elif obj_val is not None:
        # Trường hợp 1: Có Gap và Gap cực nhỏ -> Optimal thực sự
        if actual_gap is not None and actual_gap < 0.001:
            final_status = 'Optimal'
        # Trường hợp 2: PuLP báo Optimal và chạy xong rất nhanh -> Tin là Optimal
        elif status_raw == 'Optimal' and solve_duration < 50.0:
            final_status = 'Optimal'
        # Trường hợp 3: Có Gap và Gap trong ngưỡng cho phép
        elif actual_gap is not None and actual_gap <= 0.0201:
            final_status = 'Near-Optimal'
        # Trường hợp 4: Mọi trường hợp còn lại (bao gồm cả việc không đọc được Gap sau 60s)
        else:
            final_status = 'Feasible'
    else:
        final_status = 'Infeasible'

    print(f"\n[Kết quả] Trạng thái: {final_status} (Raw: {status_raw})")
    if actual_gap is not None:
        print(f"[Kết quả] Optimality Gap: {actual_gap*100:.2f}%")
    else:
        print(f"[Kết quả] Optimality Gap: Không xác định (Nghi ngờ Timeout)")
    print(f"[Kết quả] Thời gian giải: {solve_duration:.2f} giây")
    
    if final_status == 'Infeasible':
        print("\n" + "!"*60)
        print("[-] KẾT QUẢ CHẨN ĐOÁN LỖI (DIAGNOSIS):")
        
        # Gọi lại Audit để kiểm tra nguyên nhân
        is_static_feasible, audit_errors = audit_static_feasibility(data_model)
        
        if not is_static_feasible:
            print("\n>>> NGUYÊN NHÂN: LỖI DỮ LIỆU TĨNH (STATIC ERROR)")
            print("    Hệ thống phát hiện mâu thuẫn ngay ở khâu nhân sự/trình độ:")
            for err in audit_errors[:5]:
                print(f"    - {err}")
        else:
            print("\n>>> NGUYÊN NHÂN: LỖI RÀNG BUỘC ĐỘNG (DYNAMIC CONFLICT)")
            print("    Dữ liệu tĩnh (số lượng/trình độ) hoàn toàn hợp lệ.")
            print("    Lỗi xảy ra do mâu thuẫn giữa các ràng buộc chéo như:")
            print("    1. Di chuyển bất khả thi giữa 2 cơ sở (Travel Constraint).")
            print("    2. Chồng lấn thời gian ca thi (Overlap Constraint).")
            print("    3. Quá nhiều ràng buộc cứng khiến không còn phương án khả thi.")
        print("!"*60)
    elif obj_val is not None:
        print(f"[Kết quả] Giá trị hàm mục tiêu (Objective): {obj_val:.2f}")

    metrics = {
        'status': final_status,
        'solve_time': solve_duration,
        'obj_value': obj_val,
        'gap': None, 'high': None, 'low': None,
        'slack_cap': 0, 'slack_busy': 0, 'slack_qual': 0,
        'fatigue_count': 0, 'travel_count': 0,
        'actual_gap_pct': round(actual_gap * 100, 2) if 'actual_gap' in locals() and actual_gap is not None else None
    }

    if final_status in ['Optimal', 'Near-Optimal', 'Feasible']:
        # 1. Tính toán Fairness
        w_high = pulp.value(prob.variablesDict().get('W_high'))
        w_low = pulp.value(prob.variablesDict().get('W_low'))
        if w_high is not None and w_low is not None:
            metrics['gap'] = w_high - w_low
            metrics['high'] = w_high
            metrics['low'] = w_low
            
        # 2. Thống kê Slack và Penalty (Violation counts)
        # FIX: Đồng nhất logic - tất cả đều cộng giá trị (val), không cộng số lượng (1)
        for var in prob.variables():
            val = pulp.value(var)
            if val and val > 0.001:
                if 'slack_cap' in var.name: 
                    metrics['slack_cap'] += val
                elif 'slack_busy' in var.name: 
                    metrics['slack_busy'] += val  # FIX: += 1 → += val
                elif 'slack_qual' in var.name: 
                    metrics['slack_qual'] += val  # FIX: += 1 → += val
                elif 'yfatigue' in var.name: 
                    metrics['fatigue_count'] += val
                elif 'ypair' in var.name: 
                    metrics['travel_count'] += val
                
        if not skip_export:
            print(f"\n[+] ĐÃ TÌM THẤY LỜI GIẢI ({final_status})!")
            export_to_excel(prob, X, data_model)
            
    return final_status, metrics

def export_to_excel(prob, X, data_model):
    """Xuất kết quả lịch phân công ra file Excel"""
    print("Đang xuất kết quả ra file Excel...")

    CB = data_model['sets']['CB']
    CT = data_model['sets']['CT']
    R = data_model['sets']['R']
    CT_info = data_model['parameters']['CT_info']

    schedule_data = []
    for i in CB:
        for j in CT:
            for r in R:
                if pulp.value(X[i, j, r]) and pulp.value(X[i, j, r]) > 0.5:
                    info = CT_info[j]
                    h = int(info['start'])
                    m = int(round((info['start'] % 1) * 60))
                    time_str = f"{h}g{m:02d}"

                    schedule_data.append({
                        'Mã Ca Thi': info['original_id'],
                        'Ngày': info['date'].strftime('%d/%m/%Y'),
                        'Giờ Bắt Đầu': time_str,
                        'Cơ Sở': info['campus'],
                        'Mã Cán Bộ': i,
                        'Vai Trò': r,
                        '_sort_date':   info['date'],       # date object — sort đúng
                        '_sort_start':  info['start'], 
                    })

    df_result = pd.DataFrame(schedule_data)
    df_result = df_result.sort_values(by=['_sort_date', '_sort_start', 'Cơ Sở', 'Mã Ca Thi'])
    df_result = df_result.drop(columns=['_sort_date', '_sort_start'])

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    output_dir = os.path.join(project_root, 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'Optimized_Schedule.xlsx')

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_result.to_excel(writer, index=False, sheet_name='Lich_Phan_Cong')

    print(f"[+] Tuyệt vời! File kết quả đã được lưu tại: {output_file}")