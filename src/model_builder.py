import pulp

def build_model(data_model):
    """Xây dựng mô hình ILP: Khởi tạo biến, ràng buộc và hàm mục tiêu"""
    print("--- Đang khởi tạo mô hình ILP ---")
    prob = pulp.LpProblem("IAP_HCMUT", pulp.LpMinimize)
    
    # 1. Khởi tạo biến quyết định và biến nới lỏng (Slack Variables)
    X, Slacks = init_variables(data_model)
    
    # 2. Thêm Ràng buộc cứng (Đã nhúng Slack và Luật di chuyển bất khả thi)
    add_hard_constraints(prob, X, Slacks, data_model)
    
    # 3. Thêm Ràng buộc mềm, Hàm mục tiêu và Phạt Slack
    add_soft_constraints_and_objective(prob, X, Slacks, data_model)
    
    return prob, X

def init_variables(data_model):
    """Khởi tạo biến quyết định chính x_ijr và các biến nới lỏng (Slacks)"""
    CB = data_model['sets']['CB']
    CT = data_model['sets']['CT']
    R = data_model['sets']['R']
    
    # x_ijr: Biến quyết định chính (1 nếu làm, 0 nếu không)
    X = pulp.LpVariable.dicts("x", ((i, j, r) for i in CB for j in CT for r in R), cat='Binary')
    
    # Biến nới lỏng (Slack) để dùng cho Tuning Relaxation (Mục 8)
    Slacks = {
        # Số lượng người bị THIẾU cho ca j, vai trò r
        'cap': pulp.LpVariable.dicts("slack_cap", ((j, r) for j in CT for r in R), lowBound=0, cat='Integer'),
        # Cờ báo hiệu ÉP người đang bận phải đi làm
        'busy': pulp.LpVariable.dicts("slack_busy", ((i, j, r) for i in CB for j in CT for r in R), cat='Binary'),
        # Cờ báo hiệu phân công VƯỢT CẤP (thiếu năng lực)
        'qual': pulp.LpVariable.dicts("slack_qual", ((i, j, r) for i in CB for j in CT for r in R), cat='Binary')
    }
    return X, Slacks

def add_hard_constraints(prob, X, Slacks, data_model):
    """Thêm các Ràng buộc Cứng (Kèm Nới Lỏng và Di chuyển bất khả thi)"""
    CB = data_model['sets']['CB']
    CT = data_model['sets']['CT']
    R = data_model['sets']['R']
    Cap_jr = data_model['parameters']['Cap_jr']
    B_ij = data_model['parameters']['B_ij']
    CT_info = data_model['parameters']['CT_info']
    L_i = data_model['synthetic']['L_i']
    
    # --- 1. Ràng buộc Nhu cầu (Có nới lỏng) ---
    for j in CT:
        for r in R:
            req = Cap_jr.get((j, r), 0)
            if req > 0:
                prob += pulp.lpSum(X[i, j, r] for i in CB) + Slacks['cap'][j, r] == req, f"Cap_{j}_{r}"
            else:
                for i in CB:
                    prob += X[i, j, r] == 0

    # --- 2. Ràng buộc Chống trùng lịch (Cứng Tuyệt Đối) ---
    for i in CB:
        for j in CT:
            prob += pulp.lpSum(X[i, j, r] for r in R) <= 1, f"OneRole_{i}_{j}"
            
    # --- 3. Ràng buộc Trạng thái bận (Có nới lỏng) ---
    for i in CB:
        for j in CT:
            if B_ij.get((i, j), 0) == 1:
                for r in R:
                    # Nếu slack = 0 -> X = 0 (Nghiêm cấm). Nếu Slack = 1 -> X <= 1 (Được phép)
                    prob += X[i, j, r] <= Slacks['busy'][i, j, r], f"Busy_{i}_{j}_{r}"

    # --- 4. Ràng buộc Năng lực (Có nới lỏng) ---
    for i in CB:
        level = L_i.get(i, 1)
        for j in CT:
            if level < 2:
                prob += X[i, j, 'Thuky'] <= Slacks['qual'][i, j, 'Thuky'], f"Qual_Thuky_{i}_{j}"
            if level < 3:
                prob += X[i, j, 'TruongHD'] <= Slacks['qual'][i, j, 'TruongHD'], f"Qual_TruongHD_{i}_{j}"

    # --- 5. LỖ HỔNG VẬT LÝ: DI CHUYỂN BẤT KHẢ THI (Cứng Tuyệt Đối) ---
    sorted_shifts = sorted(CT, key=lambda j: (CT_info[j]['date'], CT_info[j]['start']))
    for idx1 in range(len(sorted_shifts)):
        for idx2 in range(idx1 + 1, len(sorted_shifts)):
            j1, j2 = sorted_shifts[idx1], sorted_shifts[idx2]
            info1, info2 = CT_info[j1], CT_info[j2]
            
            # Xét 2 ca nối tiếp cùng ngày
            if info1['date'] == info2['date'] and info1['end'] <= info2['start']:
                # Nếu KHÁC CƠ SỞ và Cách nhau DƯỚI 2 tiếng
                if info1['campus'] != info2['campus']:
                    if (info2['start'] - info1['end']) < 2.0:
                        # CẤM TUYỆT ĐỐI một người làm cả 2 ca này
                        for i in CB:
                            prob += pulp.lpSum(X[i, j1, r] for r in R) + pulp.lpSum(X[i, j2, r] for r in R) <= 1, f"Impossible_Travel_{i}_{j1}_{j2}"


def add_soft_constraints_and_objective(prob, X, Slacks, data_model):
    """
    Thêm Ràng buộc mềm, Bảng giá phạt và Đánh thuế Slacks
    """
    CB = data_model['sets']['CB']
    CT = data_model['sets']['CT']
    R = data_model['sets']['R']
    CT_info = data_model['parameters']['CT_info']
    L_i = data_model['synthetic']['L_i']
    Campus_like_ik = data_model['synthetic']['Campus_like_ik']

    # --- BƯỚC 1: TRỌNG SỐ TUNING ---
    omega = 1.0       # Trọng số cho tổng điểm Phạt
    theta = 20.0      # Trọng số cho sự Công bằng
    
    # Bàn tay sắt: Đánh thuế cực nặng nếu dám xài biến Nới lỏng
    TAX_LACK_STAFF = 10000.0  # Phạt 10k nếu thiếu 1 người
    TAX_FORCE_BUSY = 5000.0   # Phạt 5k nếu ép người bận
    TAX_BAD_QUAL   = 5000.0   # Phạt 5k nếu phân công vượt cấp

    # --- BƯỚC 2: MA TRẬN PHẠT TĨNH (P_ijr) ---
    req_level_map = {'CBCT': 1, 'Thuky': 2, 'TruongHD': 3}
    P_ijr = {}
    for i in CB:
        for j in CT:
            campus_j = CT_info[j]['campus']
            like_score = Campus_like_ik.get((i, campus_j), 2)
            penalty_campus = 10.0 * (1 - like_score / 3.0)
            
            for r in R:
                req_level = req_level_map.get(r, 1)
                penalty_qual = 5.0 * max(0, L_i[i] - req_level) 
                P_ijr[(i, j, r)] = penalty_campus + penalty_qual

    # --- BƯỚC 3: TÍNH TRƯỚC "BẢNG GIÁ PHẠT" ĐỘNG ---
    sorted_shifts = sorted(CT, key=lambda j: (CT_info[j]['date'], CT_info[j]['start']))
    pair_penalties = {}   
    triplet_penalties = {} 
    
    for idx1 in range(len(sorted_shifts)):
        for idx2 in range(idx1 + 1, len(sorted_shifts)):
            j1, j2 = sorted_shifts[idx1], sorted_shifts[idx2]
            info1, info2 = CT_info[j1], CT_info[j2]
            
            if info1['date'] == info2['date'] and info1['end'] <= info2['start']:
                # Luật di chuyển (Chỉ xét gap >= 2 vì < 2 đã bị Cấm Tuyệt Đối ở trên)
                if info1['campus'] != info2['campus']:
                    gap_hours = info2['start'] - info1['end']
                    if gap_hours >= 2.0:
                        penalty = max(0.0, 50.0 - 10.0 * (gap_hours - 2.0))
                        if penalty > 0:
                            pair_penalties[(j1, j2)] = penalty

                # Luật mệt mỏi: 3 ca liên tiếp Cùng cơ sở
                for idx3 in range(idx2 + 1, len(sorted_shifts)):
                    j3 = sorted_shifts[idx3]
                    info3 = CT_info[j3]
                    if info2['date'] == info3['date'] and info2['end'] <= info3['start']:
                        if info1['campus'] == info2['campus'] == info3['campus']:
                            triplet_penalties[(j1, j2, j3)] = 40.0 

    # --- BƯỚC 4: KHỞI TẠO BIẾN CỜ (FLAGS) & BIẾN CÔNG BẰNG ---
    W_i = {i: pulp.LpVariable(f"W_{i}", lowBound=0, cat='Integer') for i in CB}
    W_high = pulp.LpVariable("W_high", lowBound=0, cat='Integer')
    W_low = pulp.LpVariable("W_low", lowBound=0, cat='Integer')
    
    Y_pair = pulp.LpVariable.dicts("ypair", ((i, j1, j2) for i in CB for (j1, j2) in pair_penalties.keys()), cat='Binary')
    Y_trip = pulp.LpVariable.dicts("ytrip", ((i, j1, j2, j3) for i in CB for (j1, j2, j3) in triplet_penalties.keys()), cat='Binary')

    # --- BƯỚC 5: ÉP RÀNG BUỘC KÍCH HOẠT CỜ ---
    for i in CB:
        prob += W_i[i] == pulp.lpSum(X[i, j, r] for j in CT for r in R), f"TotalShifts_{i}"
        prob += W_high >= W_i[i], f"MaxBound_{i}"
        prob += W_low <= W_i[i], f"MinBound_{i}"
        
        for (j1, j2) in pair_penalties.keys():
            prob += Y_pair[i, j1, j2] >= pulp.lpSum(X[i, j1, r] for r in R) + pulp.lpSum(X[i, j2, r] for r in R) - 1
            
        for (j1, j2, j3) in triplet_penalties.keys():
            prob += Y_trip[i, j1, j2, j3] >= pulp.lpSum(X[i, j1, r] for r in R) + pulp.lpSum(X[i, j2, r] for r in R) + pulp.lpSum(X[i, j3, r] for r in R) - 2

    # --- BƯỚC 6: TỔNG HỢP HÀM MỤC TIÊU ---
    F1 = W_high - W_low
    
    penalty_static = pulp.lpSum(P_ijr[(i, j, r)] * X[i, j, r] for i in CB for j in CT for r in R)
    penalty_pairs = pulp.lpSum(pair_penalties[(j1, j2)] * Y_pair[i, j1, j2] for i in CB for (j1, j2) in pair_penalties.keys())
    penalty_triplets = pulp.lpSum(triplet_penalties[(j1, j2, j3)] * Y_trip[i, j1, j2, j3] for i in CB for (j1, j2, j3) in triplet_penalties.keys())
    
    # Tính "Tiền Thuế" từ các biến nới lỏng
    penalty_slack_cap = pulp.lpSum(Slacks['cap'][j, r] * TAX_LACK_STAFF for j in CT for r in R)
    penalty_slack_busy = pulp.lpSum(Slacks['busy'][i, j, r] * TAX_FORCE_BUSY for i in CB for j in CT for r in R)
    penalty_slack_qual = pulp.lpSum(Slacks['qual'][i, j, r] * TAX_BAD_QUAL for i in CB for j in CT for r in R)
    
    F2 = penalty_static + penalty_pairs + penalty_triplets + penalty_slack_cap + penalty_slack_busy + penalty_slack_qual
    
    # Gán hàm mục tiêu
    prob += omega * F2 + theta * F1, "Objective_Function"