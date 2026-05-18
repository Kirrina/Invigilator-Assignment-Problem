import pulp
import pandas as pd

def solve_model(prob, X, data_model):
    """Gọi Solver để giải bài toán ILP và xuất kết quả ra Excel"""
    print("\n--- Bắt đầu chạy Solver (PuLP) ---")
    
    # Cài đặt solver mặc định của PuLP là CBC. Có thể giới hạn thời gian chạy (timeLimit) nếu bài toán quá lớn
    status = prob.solve(pulp.PULP_CBC_CMD(msg=True))
    
    print(f"Trạng thái tối ưu: {pulp.LpStatus[status]}")
    
    if pulp.LpStatus[status] == 'Optimal':
        print("\n[+] ĐÃ TÌM THẤY LỜI GIẢI TỐI ƯU!")
        print("Đang xuất kết quả ra file Excel...")
        
        CB = data_model['sets']['CB']
        CT = data_model['sets']['CT']
        R = data_model['sets']['R']
        CT_info = data_model['parameters']['CT_info']
        
        schedule_data = []
        
        # Duyệt qua tất cả các biến quyết định để tìm những phân công được chọn (x = 1)
        for i in CB:
            for j in CT:
                for r in R:
                    # Do sai số dấu phẩy động của thuật toán giải, kiểm tra > 0.5 thay vì == 1
                    if pulp.value(X[i, j, r]) and pulp.value(X[i, j, r]) > 0.5:
                        info = CT_info[j]
                        # Chuyển đổi lại giờ float (18.25) về dạng string (18g15) cho đẹp
                        h = int(info['start'])
                        m = int(round((info['start'] % 1) * 60))
                        time_str = f"{h}g{m:02d}"
                        
                        schedule_data.append({
                            'Mã Ca Thi': j,
                            'Ngày': info['date'].strftime('%d/%m/%Y'),
                            'Giờ Bắt Đầu': time_str,
                            'Cơ Sở': info['campus'],
                            'Mã Cán Bộ': i,
                            'Vai Trò': r
                        })
        
        df_result = pd.DataFrame(schedule_data)
        
        # Sắp xếp lại lịch theo Thời gian và Cơ sở để dễ nhìn
        df_result = df_result.sort_values(by=['Ngày', 'Giờ Bắt Đầu', 'Cơ Sở', 'Mã Ca Thi'])
        
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        output_dir = os.path.join(project_root, 'output')
        os.makedirs(output_dir, exist_ok=True) # Đảm bảo thư mục output tồn tại
        output_file = os.path.join(output_dir, 'Optimized_Schedule.xlsx')
        
        # Ghi ra file Excel, tự động điều chỉnh độ rộng cột cơ bản
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False, sheet_name='Lich_Phan_Cong')
            
        print(f"[+] Tuyệt vời! File kết quả đã được lưu tại: {output_file}")
        
    else:
        print("\n[-] KHÔNG TÌM THẤY LỜI GIẢI (INFEASIBLE). Cần nới lỏng Ràng buộc cứng hoặc dữ liệu đầu vào.")