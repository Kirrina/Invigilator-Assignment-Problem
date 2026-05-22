import pulp

# Mapping chuẩn mức độ vai trò
REQ_LEVEL_MAP = {'CBCT': 1, 'Thuky': 2, 'TruongHD': 3}

def build_model(data_model, weights=None):
    """Xây dựng mô hình ILP: Khởi tạo biến, ràng buộc và hàm mục tiêu"""
    print("--- Đang khởi tạo mô hình ILP ---")
    
    # Thiết lập trọng số mặc định nếu không được truyền vào
    if weights is None:
        weights = {
            'omega': 1.0,           # Trọng số Phạt (Penalty)
            'theta': 20.0,          # Trọng số Công bằng (Fairness)
            'TAX_LACK_STAFF': 10000.0,
            'TAX_FORCE_BUSY': 5000.0,
            'TAX_BAD_QUAL': 5000.0
        }
        
    prob = pulp.LpProblem("IAP_HCMUT", pulp.LpMinimize)
    
    # 1. Khởi tạo biến quyết định và biến nới lỏng (Slack Variables)
    X, Slacks = init_variables(data_model)
    
    # 2. Thêm Ràng buộc cứng (Đã nhúng Slack và Luật di chuyển bất khả thi)
    add_hard_constraints(prob, X, Slacks, data_model)
    
    # 3. Thêm Ràng buộc mềm, Hàm mục tiêu và Phạt Slack
    add_soft_constraints_and_objective(prob, X, Slacks, data_model, weights)
    
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
        'busy': {},
        # Cờ báo hiệu phân công VƯỢT CẤP (thiếu năng lực)
        'qual': pulp.LpVariable.dicts("slack_qual", ((i, j, r) for i in CB for j in CT for r in R), cat='Binary')
    }
    return X, Slacks

def add_hard_constraints(prob, X, Slacks, data_model):
    """
    Thêm các Ràng buộc Cứng (Kèm Nới Lỏng và Di chuyển bất khả thi)
    
    Constraints added:
    1. Capacity requirements (with slack for flexibility)
    2. Overlap constraint (No double-booking for overlapping times)
    3. Busy status (with slack for forced assignment)
    4. Qualification level (with slack for underqualification)
    5. Impossible travel detection (different campus, < 2 hours gap)
    """
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
            req = Cap_jr.get((j, r), None)
            
            if req is None:
                req = 0
            elif req < 0:
                print(f"⚠️  WARNING: Invalid negative capacity {req} for Shift {j}, Role {r}")
                req = 0
            
            if req > 0:
                # Requirement with slack for extra capacity
                prob += pulp.lpSum(X[i, j, r] for i in CB) + Slacks['cap'][j, r] == req, f"Cap_{j}_{r}"
                
                # --- RULE: LEAD PROCTOR (Chặn đứng sự lỏng lẻo) ---
                # Phải có ít nhất 1 người đạt chuẩn năng lực gác vai trò này
                # Note: Chỉ xét những người không bị bận tuyệt đối (B_ij != 2)
                required_level = REQ_LEVEL_MAP.get(r, 1)
                qualified_and_free = [i for i in CB 
                                      if L_i.get(i, 1) >= required_level 
                                      and B_ij.get((i, j), 0) != 2]
                
                # Chỉ thêm constraint nếu có người phù hợp để tránh mâu thuẫn logic tức thì
                # Nếu trống, Audit Static Feasibility sẽ cảnh báo lỗi dữ liệu.
                if qualified_and_free:
                    prob += pulp.lpSum(X[i, j, r] for i in qualified_and_free) >= 1, f"LeadProctor_{j}_{r}"
                else:
                    # Nếu không có ai rảnh và đủ trình độ, vẫn ép buộc ít nhất có người đủ trình độ (dù bận)
                    # để solver báo lỗi Infeasible một cách tường minh qua xung đột ràng buộc Busy
                    qualified_staff = [i for i in CB if L_i.get(i, 1) >= required_level]
                    if qualified_staff:
                        prob += pulp.lpSum(X[i, j, r] for i in qualified_staff) >= 1, f"LeadProctor_Hard_{j}_{r}"
            else:
                for i in CB:
                    prob += X[i, j, r] == 0

    # --- 2. FIX: Ràng buộc Chống trùng lịch (Dạng tổng quát cho mọi ca chồng lấn) ---
    # Pre-calculate overlapping shift pairs
    print("   ... Đang tính toán các cặp ca chồng lấn thời gian")
    overlapping_pairs = []
    sorted_shifts = sorted(CT, key=lambda j: (CT_info[j]['date'], CT_info[j]['start']))
    
    for idx1 in range(len(sorted_shifts)):
        for idx2 in range(idx1 + 1, len(sorted_shifts)):
            j1, j2 = sorted_shifts[idx1], sorted_shifts[idx2]
            info1, info2 = CT_info[j1], CT_info[j2]
            
            if info1['date'] == info2['date']:
                if max(info1['start'], info2['start']) < min(info1['end'], info2['end']):
                    overlapping_pairs.append((j1, j2))
                elif info1['end'] == info2['start'] or info2['end'] == info1['start']:
                    overlapping_pairs.append((j1, j2))

    # TỐI ƯU HÓA: Tính trước tổng các vai trò cho mỗi người-ca
    X_sum = {(i, j): pulp.lpSum(X[i, j, r] for r in R) for i in CB for j in CT}

    for i in CB:
        for (j1, j2) in overlapping_pairs:
            prob += X_sum[i, j1] + X_sum[i, j2] <= 1, f"Overlap_{i}_{j1}_{j2}"
        
        for j in CT:
            prob += X_sum[i, j] <= 1, f"OneRolePerShift_{i}_{j}"
            
    # --- 3. Ràng buộc Trạng thái bận (Phân bậc: Tuyệt đối vs. Bận nhẹ) ---
    for i in CB:
        for j in CT:
            busy_status = B_ij.get((i, j), 0)
            if busy_status == 2:
                # Bận tuyệt đối (Hard-Busy) -> Cấm phân công
                for r in R:
                    prob += X[i, j, r] == 0, f"HardBusy_{i}_{j}_{r}"
            elif busy_status == 1:
                # Bận nhẹ (Soft-Busy) -> Cho phép nới lỏng kèm phạt
                for r in R:
                    slack_var = pulp.LpVariable(f"slack_busy_{i}_{j}_{r}", cat='Binary')
                    Slacks['busy'][(i,j,r)] = slack_var
                    prob += X[i, j, r] <= slack_var, f"SoftBusy_{i}_{j}_{r}"

    # --- 4. Ràng buộc Năng lực (Có nới lỏng) ---
    for i in CB:
        level = L_i.get(i, 1)
        for j in CT:
            if level < 2:
                prob += X[i, j, 'Thuky'] <= Slacks['qual'][i, j, 'Thuky'], f"Qual_Thuky_{i}_{j}"
            if level < 3:
                prob += X[i, j, 'TruongHD'] <= Slacks['qual'][i, j, 'TruongHD'], f"Qual_TruongHD_{i}_{j}"

    # --- 5. LỖ HỔNG VẬT LÝ: DI CHUYỂN BẤT KHẢ THI ---
    # (Chỉ xét các ca KHÔNG chồng lấn nhưng cách nhau quá gần để di chuyển giữa các cơ sở)
    for idx1 in range(len(sorted_shifts)):
        for idx2 in range(idx1 + 1, len(sorted_shifts)):
            j1, j2 = sorted_shifts[idx1], sorted_shifts[idx2]
            info1, info2 = CT_info[j1], CT_info[j2]
            
            if info1['date'] == info2['date'] and info1['end'] <= info2['start']:
                if info1['campus'] != info2['campus']:
                    # If different campus and gap < 2 hours
                    if (info2['start'] - info1['end']) < 2.0:
                        for i in CB:
                            if (j1, j2) not in overlapping_pairs:
                                prob += X_sum[i, j1] + X_sum[i, j2] <= 1, f"Travel_{i}_{j1}_{j2}"


def add_soft_constraints_and_objective(prob, X, Slacks, data_model, weights):
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
    omega = weights.get('omega', 1.0)
    theta = weights.get('theta', 20.0)
    TAX_LACK_STAFF = weights.get('TAX_LACK_STAFF', 10000.0)
    TAX_FORCE_BUSY = weights.get('TAX_FORCE_BUSY', 5000.0)
    TAX_BAD_QUAL   = weights.get('TAX_BAD_QUAL', 5000.0)

    # --- BƯỚC 2: MA TRẬN PHẠT TĨNH (P_ijr) ---
    P_ijr = {}
    for i in CB:
        for j in CT:
            campus_j = CT_info[j]['campus']
            like_score = Campus_like_ik.get((i, campus_j), 2)
            penalty_campus = 10.0 * (1 - like_score / 3.0)
            for r in R:
                staff_level = L_i[i]
                req_level = REQ_LEVEL_MAP.get(r, 1)
                # Penalty cho Qualification Mismatch:
                # - Overqualification: Người giỏi làm việc dưới level (5.0 per level)
                # - Underqualification: Người yếu làm việc trên level (50.0 per level)
                #   (Note: Underqualification cũng bị phạt qua slack_qual * TAX_BAD_QUAL=5000,
                #    nhưng công thức này giúp model tránh dự định từ đầu)
                penalty_qual = (
                    5.0 *max(0, staff_level - req_level)   # Overqualification
                           # Underqualification
                )
                P_ijr[(i, j, r)] = penalty_campus + penalty_qual

    # --- BƯỚC 3: TÍNH TRƯỚC "BẢNG GIÁ PHẠT" ĐỘNG ---
    sorted_shifts = sorted(CT, key=lambda j: (CT_info[j]['date'], CT_info[j]['start']))
    pair_penalties = {}   
    shifts_by_day = {}
    for j in CT:
        d = CT_info[j]['date']
        if d not in shifts_by_day: shifts_by_day[d] = []
        shifts_by_day[d].append(j)

    for idx1 in range(len(sorted_shifts)):
        for idx2 in range(idx1 + 1, len(sorted_shifts)):
            j1, j2 = sorted_shifts[idx1], sorted_shifts[idx2]
            info1, info2 = CT_info[j1], CT_info[j2]
            if info1['date'] == info2['date'] and info1['end'] <= info2['start']:
                gap = info2['start'] - info1['end']
                if info1['campus'] != info2['campus'] and gap >= 2.0:
                    penalty = max(0.0, 50.0 - 10.0 * (gap - 2.0))
                    if penalty > 0: pair_penalties[(j1, j2)] = pair_penalties.get((j1, j2), 0.0) + penalty
                if gap > 2.0:
                    pair_penalties[(j1, j2)] = pair_penalties.get((j1, j2), 0.0) +   (gap - 2.0) * 15.0

    # LỌC CÁC PENALTY NHỎ ĐỂ GIẢM SỐ LƯỢNG BIẾN Y_pair (Tối ưu Memory & Performance)
    # Loại bỏ các penalty dưới 5.0 để tránh tạo biến cho những khoảng chờ không đáng kể
    MIN_PENALTY_THRESHOLD = 5.0
    pair_penalties = {k: v for k, v in pair_penalties.items() if v >= MIN_PENALTY_THRESHOLD}

    # --- BƯỚC 4: KHỞI TẠO BIẾN CỜ (FLAGS) ---
    W_i = {i: pulp.LpVariable(f"W_{i}", lowBound=0, cat='Integer') for i in CB}
    W_high = pulp.LpVariable("W_high", lowBound=0, cat='Integer')
    W_low = pulp.LpVariable("W_low", lowBound=0, cat='Integer')
    Y_pair = pulp.LpVariable.dicts("ypair", ((i, j1, j2) for i in CB for (j1, j2) in pair_penalties.keys()), cat='Binary')
    
    DAYS = list(shifts_by_day.keys())
    Y_fatigue = pulp.LpVariable.dicts("yfatigue", ((i, d, level) for i in CB for d in DAYS for level in [3, 4, 5]), cat='Binary')

    # TỐI ƯU HÓA BỘ NHỚ: Dùng sum() Python thông thường thay vì pulp.lpSum() do R rất nhỏ (3 phần tử)
    # Điều này tạo Expression nhanh hơn và tiết kiệm một chút overhead của lpSum
    X_sum = {(i, j): sum([X[i, j, r] for r in R]) for i in CB for j in CT}

    # --- BƯỚC 5: ÉP RÀNG BUỘC KÍCH HOẠT CỜ ---
    for i in CB:
        prob += W_i[i] == pulp.lpSum(X_sum[i, j] for j in CT), f"TotalShifts_{i}"
        prob += W_high >= W_i[i], f"MaxBound_{i}"
        prob += W_low <= W_i[i], f"MinBound_{i}"
        for (j1, j2) in pair_penalties.keys():
            prob += Y_pair[i, j1, j2] >= X_sum[i, j1] + X_sum[i, j2] - 1
        for d in DAYS:
            daily_total = pulp.lpSum(X_sum[i, j] for j in shifts_by_day[d])
            prob += daily_total <= 2 + Y_fatigue[i, d, 3] + Y_fatigue[i, d, 4] + Y_fatigue[i, d, 5], f"Fatigue_{i}_{d}"
            prob += Y_fatigue[i, d, 4] <= Y_fatigue[i, d, 3]
            prob += Y_fatigue[i, d, 5] <= Y_fatigue[i, d, 4]

    # --- BƯỚC 6: TỔNG HỢP HÀM MỤC TIÊU ---
    F1 = W_high - W_low
    penalty_static = pulp.lpSum(P_ijr[(i, j, r)] * X[i, j, r] for i in CB for j in CT for r in R)
    penalty_pairs = pulp.lpSum(pair_penalties[(j1, j2)] * Y_pair[i, j1, j2] for i in CB for (j1, j2) in pair_penalties.keys())
    penalty_fatigue = pulp.lpSum(40 * Y_fatigue[i, d, 3] + 80 * Y_fatigue[i, d, 4] + 150 * Y_fatigue[i, d, 5] for i in CB for d in DAYS)
    
    penalty_slack_cap = pulp.lpSum(Slacks['cap'][j, r] * TAX_LACK_STAFF for j, r in Slacks['cap'].keys())
    penalty_slack_busy = pulp.lpSum(Slacks['busy'][i, j, r] * TAX_FORCE_BUSY for i, j, r in Slacks['busy'].keys())
    penalty_slack_qual = pulp.lpSum(Slacks['qual'][i, j, r] * TAX_BAD_QUAL for i, j, r in Slacks['qual'].keys())
    
    F2 = penalty_static + penalty_pairs + penalty_fatigue + penalty_slack_cap + penalty_slack_busy + penalty_slack_qual
    prob += omega * F2 + theta * F1, "Objective_Function"
