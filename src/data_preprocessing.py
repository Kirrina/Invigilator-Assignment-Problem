import pandas as pd
import numpy as np
import random

def convert_time_to_float(time_str):
    try:
        h, m = time_str.lower().split('g')
        return int(h) + int(m)/60
    except:
        return 0.0

def normalize_role(role):
    role = role.strip().lower()

    mapping = {
        'cbct': 'CBCT',
        'thư ký': 'Thuky',
        'trưởng hđ': 'TruongHD'
    }

    return mapping.get(role, role)

def preprocess_data(file_path):
    print(f"Đang đọc dữ liệu từ: {file_path}")
    df = pd.read_excel(file_path)

    CB = df['MS của CÁN BỘ COI THI'].dropna().unique().tolist()
    CT = df['MS Ca thi'].dropna().unique().tolist()
    K = df['Cơ sở'].dropna().unique().tolist()

    df['Vai_tro'] = (df['Nhiệm vụ'].astype(str).apply(lambda x: normalize_role(x.split('_')[-1])))
    R = df['Vai_tro'].unique().tolist()

    CT_info = {}
    shift_metadata = df[['MS Ca thi', 'Ngày', 'GIỜ', 'Thời gian', 'Cơ sở']].drop_duplicates()
    
    for _, row in shift_metadata.iterrows():
        sid = row['MS Ca thi']
        start_t = convert_time_to_float(str(row['GIỜ']))
        duration = row['Thời gian'] / 60
        pure_date = pd.to_datetime(row['Ngày']).date()
        CT_info[sid] = {
            'date': pure_date,
            'start': start_t,
            'end': start_t + duration,
            'campus': row['Cơ sở']
        }

    cap_series = df.groupby(['MS Ca thi', 'Vai_tro'])['MS của CÁN BỘ COI THI'].count()
    Cap_jr = cap_series.to_dict()

    B_ij = {(i, j): 0 for i in CB for j in CT}
    num_busy_slots = int(0.05 * len(CB) * len(CT))
    busy_pairs = random.sample(list(B_ij.keys()), num_busy_slots)
    for pair in busy_pairs:
        B_ij[pair] = 1

    np.random.seed(42)
    random.seed(42)

    role_level_map = {'CBCT': 1, 'Thuky': 2, 'TruongHD': 3}
    L_i = {}
    for i in CB:
        roles_done = df[df['MS của CÁN BỘ COI THI'] == i]['Vai_tro'].unique()
        levels = [role_level_map.get(r, 1) for r in roles_done]
        L_i[i] = max(levels) if levels else 3

    groups = ['Nhom_CS1', 'Nhom_CS2', 'Nhom_CanBang']
    Campus_like_ik = {}
    for i in CB:
        assigned_group = random.choice(groups)
        if assigned_group == 'Nhom_CS1':
            Campus_like_ik[(i, 'Cơ sở 1')] = 3
            Campus_like_ik[(i, 'Cơ sở 2')] = 1
        elif assigned_group == 'Nhom_CS2':
            Campus_like_ik[(i, 'Cơ sở 1')] = 1
            Campus_like_ik[(i, 'Cơ sở 2')] = 3
        else:
            Campus_like_ik[(i, 'Cơ sở 1')] = 2
            Campus_like_ik[(i, 'Cơ sở 2')] = 2

    print("--- Hoàn tất tiền xử lý dữ liệu ---")
    
    return {
        'sets': {'CB': CB, 'CT': CT, 'R': R, 'K': K},
        'parameters': {'Cap_jr': Cap_jr, 'B_ij': B_ij, 'CT_info': CT_info},
        'synthetic': {'L_i': L_i, 'Campus_like_ik': Campus_like_ik}
    }

def manual_data_adjustment(data_model):
    CB = data_model['sets']['CB']
    CT = data_model['sets']['CT']
    K = data_model['sets']['K']
    L_i = data_model['synthetic']['L_i']
    Campus_like_ik = data_model['synthetic']['Campus_like_ik']
    B_ij = data_model['parameters']['B_ij']

    while True:
        print("\n" + "="*50)
        print("   HỆ THỐNG ĐIỀU CHỈNH DỮ LIỆU ĐẦU VÀO (DATA ADJUSTMENT)")
        print("="*50)
        print("1. Xem chi tiết thông tin 1 cán bộ")
        print("2. Thay đổi năng lực chuyên môn (L_i)")
        print("3. Thay đổi sở thích cơ sở (Campus_like_ik)")
        print("4. Thay đổi trạng thái bận việc riêng (B_ij)")
        print("0. Hoàn tất và chuẩn bị chạy Solver")
        print("-" * 50)
        
        choice = input("Nhập lựa chọn của bạn (0-4): ").strip()
        
        if choice == '0':
            print(">>> Dữ liệu đã sẵn sàng.")
            break
        elif choice == '1':
            staff_id = input("Nhập mã cán bộ (VD: CB001): ").strip()
            if staff_id in CB:
                print(f"\n[Dữ liệu hiện tại của {staff_id}]:")
                print(f"- Năng lực (L_i): {L_i[staff_id]}")
                for k in K:
                    print(f"- Mức độ thích {k}: {Campus_like_ik.get((staff_id, k))}")
                busy_shifts = [j for j in CT if B_ij.get((staff_id, j)) == 1]
                print(f"- Số ca thi đang bị bận (B_ij=1): {len(busy_shifts)}")
            else:
                print("(!) Mã cán bộ không tồn tại.")
        elif choice == '2':
            staff_id = input("Nhập mã cán bộ: ").strip()
            if staff_id in CB:
                try:
                    new_val = int(input("Nhập năng lực mới (1, 2 hoặc 3): "))
                    if new_val in [1, 2, 3]:
                        L_i[staff_id] = new_val
                    else:
                        print("(!) Giá trị phải là 1, 2 hoặc 3.")
                except ValueError:
                    print("(!) Vui lòng nhập số.")
        elif choice == '3':
            staff_id = input("Nhập mã cán bộ: ").strip()
            if staff_id in CB:
                try:
                    for k in K:
                        new_val = int(input(f" - Mức thích {k} (1: Ghét, 2: BT, 3: Thích): "))
                        if new_val in [1, 2, 3]:
                            Campus_like_ik[(staff_id, k)] = new_val
                except ValueError:
                    print("(!) Vui lòng nhập số.")
        elif choice == '4':
            staff_id = input("Nhập mã cán bộ: ").strip()
            shift_id = input("Nhập mã ca thi: ").strip()
            if (staff_id in CB) and (shift_id in CT):
                try:
                    new_val = int(input("Trạng thái bận (1: Bận, 0: Rảnh): "))
                    if new_val in [0, 1]:
                        B_ij[(staff_id, shift_id)] = new_val
                except ValueError:
                    print("(!) Vui lòng nhập số.")