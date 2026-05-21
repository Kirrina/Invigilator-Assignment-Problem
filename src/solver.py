import pulp
import pandas as pd
import os
import time

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

    # Logic phân loại trạng thái nghiệm (Refactoring Step 2)
    if status_raw == 'Optimal':
        final_status = 'Optimal'
    elif obj_val is not None:
        # Nếu không báo Optimal nhưng đã có nghiệm trong tay (do đạt TimeLimit hoặc Gap)
        if solve_duration < 59.0: # Dừng trước khi hết giờ -> Chắc chắn đạt Gap 2%
            final_status = 'Near-Optimal'
        else: # Bị ngắt do hết giờ -> Có nghiệm nhưng chưa chứng minh được Gap
            final_status = 'Feasible'
    else:
        final_status = 'Infeasible'

    print(f"\n[Kết quả] Trạng thái: {final_status} (Raw: {status_raw})")
    print(f"[Kết quả] Thời gian giải: {solve_duration:.2f} giây")
    if obj_val is not None:
        print(f"[Kết quả] Giá trị hàm mục tiêu (Objective): {obj_val:.2f}")

    metrics = {
        'status': final_status,
        'solve_time': solve_duration,
        'obj_value': obj_val,
        'gap': None, 'high': None, 'low': None,
        'slack_cap': 0, 'slack_busy': 0, 'slack_qual': 0,
        'fatigue_count': 0, 'travel_count': 0
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
        for var in prob.variables():
            val = pulp.value(var)
            if val and val > 0.001:
                if 'slack_cap' in var.name: metrics['slack_cap'] += val
                elif 'slack_busy' in var.name: metrics['slack_busy'] += 1
                elif 'slack_qual' in var.name: metrics['slack_qual'] += 1
                elif 'yfatigue' in var.name: metrics['fatigue_count'] += 1
                elif 'ypair' in var.name: metrics['travel_count'] += 1
                
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
                        'Vai Trò': r
                    })

    df_result = pd.DataFrame(schedule_data)
    df_result = df_result.sort_values(by=['Ngày', 'Giờ Bắt Đầu', 'Cơ Sở', 'Mã Ca Thi'])

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    output_dir = os.path.join(project_root, 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'Optimized_Schedule.xlsx')

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_result.to_excel(writer, index=False, sheet_name='Lich_Phan_Cong')

    print(f"[+] Tuyệt vời! File kết quả đã được lưu tại: {output_file}")