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
            
        # 2. Thống kê Slack và cờ vi phạm
        #
        # ĐỒNG BỘ VỚI model_builder.py:
        #   slack_busy, slack_qual là biến Binary → += val (không phải += 1)
        #   yfatigue có 3 mức per (staff, day): level=3 (+40), level=4 (+80), level=5 (+150)
        #     → penalty cộng dồn: 3 ca/ngày=40, 4 ca=120, 5 ca=270
        #   ypair: += val (binary flag)
        M4_fatigue = 0.0
        for var in prob.variables():
            val = pulp.value(var)
            if val is None or val <= 0.001:
                continue
            name = var.name
            if 'slack_cap' in name:
                metrics['slack_cap'] += val
            elif 'slack_busy' in name:
                metrics['slack_busy'] += val          # tổng giá trị, không phải count
            elif 'slack_qual' in name:
                metrics['slack_qual'] += val          # tổng giá trị, không phải count
            elif name.startswith('yfatigue'):
                metrics['fatigue_count'] += val       # số lần kích hoạt cờ
                try:
                    level = int(name.split('_')[-1])
                    # Mỗi flag cộng thêm phần penalty của mức đó (cộng dồn)
                    if level == 3:   M4_fatigue += 40  * val
                    elif level == 4: M4_fatigue += 80  * val
                    elif level == 5: M4_fatigue += 150 * val
                except (ValueError, IndexError):
                    pass
            elif name.startswith('ypair'):
                metrics['travel_count'] += val

        # 3. Tính M3 / M5 từ coefficients hàm mục tiêu
        #
        # ĐỒNG BỘ VỚI model_builder.py — P_ijr bao gồm:
        #   penalty_campus = 10.0 * (1 - like_score / 3.0)
        #   penalty_qual   = 5.0  * max(0, staff_level - req_level)   [overqualification]
        #                  + 50.0 * max(0, req_level  - staff_level)  [underqualification — MỚI]
        # M5 = pair_penalties * ypair (travel + idle time)
        # Các coefficient trong prob.objective đã nhân omega → giá trị lấy ra là omega * penalty
        M3_static = 0.0
        M5_travel = 0.0
        try:
            for var, coeff in prob.objective.items():
                val = pulp.value(var)
                if val is None or val <= 0.001:
                    continue
                vname = var.name
                if vname.startswith('ypair'):
                    M5_travel += coeff * val
                elif vname.startswith('x_'):
                    M3_static += coeff * val
        except Exception:
            pass

        metrics['M3_static_penalty']  = round(M3_static,  2)
        metrics['M4_fatigue_penalty'] = round(M4_fatigue, 2)
        metrics['M5_travel_penalty']  = round(M5_travel,  2)
        metrics['M1_total_quality']   = round(M3_static + M4_fatigue + M5_travel, 2)

        # 4. Thêm objective vào metrics để analysis.py dùng trực tiếp
        metrics['objective'] = obj_val

        # 5. Workload distribution {staff_id: số ca}
        CB = data_model['sets']['CB']
        CT = data_model['sets']['CT']
        R  = data_model['sets']['R']
        workload_dist = {}
        for i in CB:
            count = sum(
                1 for j in CT for r in R
                if pulp.value(X[i, j, r]) is not None and pulp.value(X[i, j, r]) > 0.5
            )
            if count > 0:
                workload_dist[str(i)] = count
        metrics['_workload_dist'] = workload_dist

        # 6. Lưu metrics cho mọi trạng thái khả thi (Optimal / Near-Optimal / Feasible)
        try:
            from analysis import save_solver_metrics
            save_solver_metrics(metrics)
        except ImportError:
            pass

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
