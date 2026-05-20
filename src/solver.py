import pulp
import pandas as pd
import os

def solve_model(prob, X, data_model, skip_export=False):
    """Giải mô hình và trả về các chỉ số đánh giá chi tiết"""
    print("\n--- Bắt đầu chạy Solver (PuLP) ---")

    # timeLimit: tránh treo máy
    status = prob.solve(pulp.PULP_CBC_CMD(msg=True, timeLimit=60))
    status_str = pulp.LpStatus[status]

    print(f"Trạng thái tối ưu: {status_str}")
    
    metrics = {
        'gap': None, 'high': None, 'low': None,
        'slack_cap': 0, 'slack_busy': 0, 'slack_qual': 0,
        'fatigue_count': 0, 'travel_count': 0
    }

    if status_str == 'Optimal':
        # 1. Tính toán Fairness
        w_high = pulp.value(prob.variablesDict().get('W_high'))
        w_low = pulp.value(prob.variablesDict().get('W_low'))
        if w_high is not None and w_low is not None:
            metrics['gap'] = w_high - w_low
            metrics['high'] = w_high
            metrics['low'] = w_low
            
        # 2. Thống kê Slack và Penalty
        for var in prob.variables():
            val = pulp.value(var)
            if val and val > 0.001:
                if 'slack_cap' in var.name: metrics['slack_cap'] += val
                elif 'slack_busy' in var.name: metrics['slack_busy'] += 1
                elif 'slack_qual' in var.name: metrics['slack_qual'] += 1
                elif 'ytrip' in var.name: metrics['fatigue_count'] += 1
                elif 'ypair' in var.name: metrics['travel_count'] += 1
                
        if not skip_export:
            print("\n[+] ĐÃ TÌM THẤY LỜI GIẢI TỐI ƯU!")
            export_to_excel(prob, X, data_model)
            
    return status_str, metrics

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