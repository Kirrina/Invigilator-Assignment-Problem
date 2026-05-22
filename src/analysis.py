import os
import json
import math
import pandas as pd
import numpy as np

from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# PHẦN 1: TIỆN ÍCH JSON CACHE
# ─────────────────────────────────────────────────────────────────────────────

def _get_cache_dir():
    """Trả về đường dẫn thư mục output — dùng cùng logic với solver.py.

    Cấu trúc project giả định:
        project_root/
        ├── output/        ← JSON cache 
        └── src/           
            ├── analysis.py
            ├── solver.py
            └── ...
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)   # src/ -> project_root/
    output_dir = os.path.join(project_root, 'output')
    
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _serialize_key(k):
    """Chuyển tuple key → string để lưu JSON (vì JSON không hỗ trợ tuple key)."""
    if isinstance(k, tuple):
        return "|||".join(str(x) for x in k)
    return str(k)


def _deserialize_key(s, num_parts=2):
    """Khôi phục tuple key từ string JSON."""
    parts = s.split("|||")
    if len(parts) == num_parts:
        return tuple(parts)
    return s


def save_cache(B_ij: dict, Campus_like_ik: dict, output_dir: str = None):
    """
    Lưu B_ij và Campus_like_ik ra file JSON cache.
    Gọi hàm này sau khi sinh ngẫu nhiên ở lần chạy đầu tiên.
    """
    if output_dir is None:
        output_dir = _get_cache_dir()

    b_path = os.path.join(output_dir, 'B_ij_cache.json')
    c_path = os.path.join(output_dir, 'Campus_like_cache.json')

    b_serializable = {_serialize_key(k): v for k, v in B_ij.items()}
    c_serializable = {_serialize_key(k): v for k, v in Campus_like_ik.items()}

    with open(b_path, 'w', encoding='utf-8') as f:
        json.dump(b_serializable, f, ensure_ascii=False, indent=2)

    with open(c_path, 'w', encoding='utf-8') as f:
        json.dump(c_serializable, f, ensure_ascii=False, indent=2)

    print(f"[Cache] ✓ Đã lưu B_ij_cache.json ({len(b_serializable)} entries)")
    print(f"[Cache] ✓ Đã lưu Campus_like_cache.json ({len(c_serializable)} entries)")


def load_cache(output_dir: str = None):
    """
    Đọc B_ij và Campus_like_ik từ file JSON cache.
    Trả về (B_ij, Campus_like_ik) hoặc (None, None) nếu cache chưa tồn tại.
    """
    if output_dir is None:
        output_dir = _get_cache_dir()

    b_path = os.path.join(output_dir, 'B_ij_cache.json')
    c_path = os.path.join(output_dir, 'Campus_like_cache.json')

    if not os.path.exists(b_path) or not os.path.exists(c_path):
        return None, None

    with open(b_path, 'r', encoding='utf-8') as f:
        b_raw = json.load(f)
    with open(c_path, 'r', encoding='utf-8') as f:
        c_raw = json.load(f)

    B_ij = {_deserialize_key(k, 2): v for k, v in b_raw.items()}
    Campus_like_ik = {_deserialize_key(k, 2): v for k, v in c_raw.items()}

    print(f"[Cache] ✓ Đã tải B_ij_cache.json ({len(B_ij)} entries)")
    print(f"        ✓ Đã tải Campus_like_cache.json ({len(Campus_like_ik)} entries)")

    return B_ij, Campus_like_ik


def cache_exists(output_dir: str = None) -> bool:
    """Kiểm tra xem cache đã tồn tại chưa."""
    if output_dir is None:
        output_dir = _get_cache_dir()
    b_path = os.path.join(output_dir, 'B_ij_cache.json')
    c_path = os.path.join(output_dir, 'Campus_like_cache.json')
    return os.path.exists(b_path) and os.path.exists(c_path)


def save_solver_metrics(metrics: dict, output_dir: str = None):
    """Ghi metrics của Solver ra solver_metrics.json."""
    if output_dir is None:
        output_dir = _get_cache_dir()
    path = os.path.join(output_dir, 'solver_metrics.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"[Cache] ✓ Đã lưu solver_metrics.json")


def load_solver_metrics(output_dir: str = None) -> dict:
    """Đọc solver_metrics.json. Trả về dict rỗng nếu không tìm thấy."""
    if output_dir is None:
        output_dir = _get_cache_dir()
    path = os.path.join(output_dir, 'solver_metrics.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# PHẦN 2: TÍNH METRICS CHO BASELINE (LỊCH GỐC)

def _normalize_role(role_str: str) -> str:
    """Chuẩn hóa tên vai trò (giống data_preprocessing.py)."""
    role = str(role_str).strip().lower()
    mapping = {'cbct': 'CBCT', 'thư ký': 'Thuky', 'trưởng hđ': 'TruongHD'}
    return mapping.get(role, role)


def _convert_time_to_float(time_str) -> float:
    """Chuyển đổi chuỗi thời gian sang float giờ."""
    if time_str is None or (isinstance(time_str, float) and pd.isna(time_str)):
        raise ValueError("Time value is None or NaN")
    s = str(time_str).lower().strip()
    s = s.replace('giờ', '').replace('phút', '').replace(':', ' ').replace('g', ' ')
    s = ' '.join(s.split())
    parts = s.split()
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return h + m / 60.0


def compute_baseline_metrics(file_excel: str, B_ij: dict, Campus_like_ik: dict,
                              L_i: dict, CT_info: dict,
                              weights: dict = None) -> dict:
   
    if weights is None:
        weights = {
            'omega': 1.0, 'theta': 20.0,
            'TAX_LACK_STAFF': 10000.0,
            'TAX_FORCE_BUSY': 5000.0,
            'TAX_BAD_QUAL': 5000.0
        }

    print("\n[Baseline] Đang quét lịch gốc từ Excel...")
    df = pd.read_excel(file_excel)

    # Tái tạo Unique_Shift_ID giống preprocess_data
    def extract_campus(row):
        campus = row['Cơ sở']
        if pd.isna(campus) or str(campus).strip() == '':
            task = str(row['Nhiệm vụ'])
            if '_' in task:
                code = task.split('_')[0]
                if code == 'LTK': return 'Cơ sở 1'
                if code == 'DiAn': return 'Cơ sở 2'
                return code
            return "Unknown"
        return str(campus).strip()

    df['Cơ sở'] = df.apply(extract_campus, axis=1)
    df['Unique_Shift_ID'] = df['MS Ca thi'].astype(str) + "|" + df['Cơ sở']
    df['Vai_tro'] = df['Nhiệm vụ'].astype(str).apply(lambda x: _normalize_role(x.split('_')[-1]))

    req_level_map = {'CBCT': 1, 'Thuky': 2, 'TruongHD': 3}

    # ── Duyệt từng dòng phân công ──────────────────────────────────────────
    slack_busy = 0       # M7: Số ca ép người bận
    slack_qual = 0       # M8: Số ca sai chuyên môn
    penalty_static = 0.0 # M3: Phạt tĩnh (nguyện vọng)

    staff_shift_count = {}   # {i: set of shift IDs}
    staff_daily_count = {}   # {(i, date): count}
    assignments = []         # [(i, j, r, date, start, end, campus)]

    for _, row in df.iterrows():
        i = row['MS của CÁN BỘ COI THI']
        j = row['Unique_Shift_ID']
        r = row['Vai_tro']

        if pd.isna(i) or pd.isna(j):
            continue

        # Lấy thông tin ca thi
        info = CT_info.get(j)
        if info is None:
            continue

        # M7 — Ép người bận
        if B_ij.get((i, j), 0) == 1:
            slack_busy += 1

        # M8 — Sai chuyên môn
        staff_level = L_i.get(i, 1)
        required_level = req_level_map.get(r, 1)
        if staff_level < required_level:
            slack_qual += 1

        # M3 — Phạt tĩnh (campus + lãng phí năng lực)
        campus_j = info['campus']
        like_score = Campus_like_ik.get((i, campus_j), 2)
        p_campus = 10.0 * (1 - like_score / 3.0)
        p_qual = 5.0 * max(0, staff_level - required_level)
        penalty_static += p_campus + p_qual

        # Ghi nhận phân công
        if i not in staff_shift_count:
            staff_shift_count[i] = set()
        staff_shift_count[i].add(j)

        day_key = (i, info['date'])
        staff_daily_count[day_key] = staff_daily_count.get(day_key, 0) + 1

        assignments.append((i, j, r, info['date'], info['start'], info['end'], info['campus']))

    # ── M2: Fairness Gap ───────────────────────────────────────────────────
    counts = [len(v) for v in staff_shift_count.values()]
    w_high = max(counts) if counts else 0
    w_low = min(counts) if counts else 0
    fairness_gap = w_high - w_low

    # ── M4: Fatigue Penalty ────────────────────────────────────────────────
    penalty_fatigue = 0.0
    fatigue_details = {}  # {(i,d): count}
    for (i, d), cnt in staff_daily_count.items():
        fatigue_details[(i, d)] = cnt
        if cnt == 3:
            penalty_fatigue += 40
        elif cnt == 4:
            penalty_fatigue += 120
        elif cnt >= 5:
            penalty_fatigue += 270

    # ── M5: Travel & Idle Time Penalty ────────────────────────────────────
    # Nhóm phân công theo (staff, date), sắp xếp theo start
    from collections import defaultdict
    staff_day_shifts = defaultdict(list)
    for (i, j, r, d, start, end, campus) in assignments:
        staff_day_shifts[(i, d)].append((start, end, campus, j))

    penalty_pairs = 0.0
    travel_count = 0
    idle_count = 0

    for (i, d), shifts in staff_day_shifts.items():
        shifts_sorted = sorted(shifts, key=lambda x: x[0])
        for idx in range(len(shifts_sorted) - 1):
            s1_start, s1_end, campus1, j1 = shifts_sorted[idx]
            s2_start, s2_end, campus2, j2 = shifts_sorted[idx + 1]

            if s1_end <= s2_start:
                gap = s2_start - s1_end
                p = 0.0
                if campus1 != campus2 and gap >= 2.0:
                    p += max(0.0, 50.0 - 10.0 * (gap - 2.0))
                    travel_count += 1
                if gap > 2.0:
                    p += (gap - 2.0) * 15.0
                    idle_count += 1
                penalty_pairs += p

    # ── M6: Thiếu nhân sự (Capacity Slack) ────────────────────────────────
    # Đếm số người thực tế được phân cho mỗi (ca, vai trò)
    from collections import Counter
    actual_cap = Counter()
    for (i, j, r, d, start, end, campus) in assignments:
        actual_cap[(j, r)] += 1

    # Tính Cap_jr yêu cầu từ dữ liệu gốc (cách đơn giản: đếm từ Excel)
    cap_series = df.groupby(['Unique_Shift_ID', 'Vai_tro'])['MS của CÁN BỘ COI THI'].count()
    Cap_jr_required = cap_series.to_dict()
    # Lịch gốc thường không thiếu người (đây là lịch đã lên), nhưng ta vẫn tính
    slack_cap = 0
    for (j, r), req in Cap_jr_required.items():
        actual = actual_cap.get((j, r), 0)
        if actual < req:
            slack_cap += (req - actual)

    # ── Tổng hợp hàm mục tiêu ─────────────────────────────────────────────
    omega = weights['omega']
    theta = weights['theta']
    TAX_LACK_STAFF = weights['TAX_LACK_STAFF']
    TAX_FORCE_BUSY = weights['TAX_FORCE_BUSY']
    TAX_BAD_QUAL   = weights['TAX_BAD_QUAL']

    M1 = penalty_static + penalty_pairs + penalty_fatigue
    M2 = fairness_gap
    M3 = penalty_static
    M4 = penalty_fatigue
    M5 = penalty_pairs
    M6 = slack_cap * TAX_LACK_STAFF
    M7 = slack_busy * TAX_FORCE_BUSY
    M8 = slack_qual * TAX_BAD_QUAL

    objective = theta * M2 + omega * (M3 + M5 + M4) + M6 + M7 + M8

    # Phân phối workload
    _workload_dist = {i: len(v) for i, v in staff_shift_count.items()}

    metrics = {
        # Raw counts (số lượng vi phạm)
        'slack_cap':      slack_cap,
        'slack_busy':     slack_busy,
        'slack_qual':     slack_qual,
        'fatigue_count':  sum(1 for cnt in fatigue_details.values() if cnt > 2),
        'travel_count':   travel_count,
        'idle_count':     idle_count,
        'gap':            fairness_gap,
        'w_high':         w_high,
        'w_low':          w_low,
        # Điểm phạt từng thành phần
        'M1_total_quality':   M1,
        'M2_fairness_gap':    M2,
        'M3_static_penalty':  M3,
        'M4_fatigue_penalty': M4,
        'M5_travel_penalty':  M5,
        'M6_penalty_cap':     M6,
        'M7_penalty_busy':    M7,
        'M8_penalty_qual':    M8,
        # Hàm mục tiêu tổng thể
        'objective': objective,
        # Metadata
        'num_assignments': len(assignments),
        'num_staff':       len(staff_shift_count),
        # Dữ liệu phân phối cho biểu đồ workload
        '_workload_dist':  _workload_dist,
    }

    print(f"[Baseline] ✓ Đã tính xong: {len(assignments)} phân công, {len(staff_shift_count)} cán bộ")
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# PHẦN 3: SINH DASHBOARD VÀ BIỂU ĐỒ SO SÁNH
# ─────────────────────────────────────────────────────────────────────────────

def generate_dashboard_and_plots(baseline_metrics: dict, solver_metrics_raw: dict,
                                  weights: dict = None, output_dir: str = None):
    """
    In bảng đối sánh toán học và xuất 3 biểu đồ so sánh Baseline vs Solver.

    Parameters
    ----------
    baseline_metrics    : Dict trả về bởi compute_baseline_metrics()
    solver_metrics_raw  : Dict từ solver_metrics.json (output của solve_model)
    weights             : Trọng số phạt
    output_dir          : Nơi lưu file PNG (mặc định: output/)
    """
    if weights is None:
        weights = {
            'omega': 1.0, 'theta': 20.0,
            'TAX_LACK_STAFF': 10000.0,
            'TAX_FORCE_BUSY': 5000.0,
            'TAX_BAD_QUAL': 5000.0
        }
    if output_dir is None:
        output_dir = _get_cache_dir()

    TAX_LACK_STAFF = weights['TAX_LACK_STAFF']
    TAX_FORCE_BUSY = weights['TAX_FORCE_BUSY']
    TAX_BAD_QUAL   = weights['TAX_BAD_QUAL']
    theta          = weights['theta']
    omega          = weights['omega']

    # ── Tái tạo metrics đầy đủ cho Solver từ raw dict ──────────────────────
    s = solver_metrics_raw  # alias ngắn
    solver_slack_cap   = float(s.get('slack_cap', 0))
    solver_slack_busy  = float(s.get('slack_busy', 0))
    solver_slack_qual  = float(s.get('slack_qual', 0))
    solver_gap         = float(s.get('gap', 0) or 0)
    solver_w_high      = float(s.get('high', 0) or 0)
    solver_w_low       = float(s.get('low', 0) or 0)
    solver_fatigue_cnt = float(s.get('fatigue_count', 0))
    solver_travel_cnt  = float(s.get('travel_count', 0))

    solver_M6 = solver_slack_cap * TAX_LACK_STAFF
    solver_M7 = solver_slack_busy * TAX_FORCE_BUSY
    solver_M8 = solver_slack_qual * TAX_BAD_QUAL
    # M3+M4+M5 của solver: lấy từ objective nếu có, nếu không dùng giá trị lưu
    solver_quality_penalty = float(s.get('M1_total_quality', s.get('quality_penalty', 0)))
    # Breakdown M3/M4/M5 từ solver_metrics.json (được lưu bởi solver.py đã sửa)
    s_m3 = float(s.get('M3_static_penalty',  0.0))
    s_m4 = float(s.get('M4_fatigue_penalty', 0.0))
    s_m5 = float(s.get('M5_travel_penalty',  0.0))
    if s_m3 == 0 and s_m4 == 0 and s_m5 == 0 and solver_quality_penalty > 0:
        s_m3 = solver_quality_penalty
        print("⚠️  [Analysis] Chua co breakdown M3/M4/M5 — hien thi M1 gop vao M3.")
    solver_M2 = solver_gap
    solver_objective = float(s.get('objective',
                             theta * solver_M2 + omega * (s_m3 + s_m4 + s_m5) + solver_M6 + solver_M7 + solver_M8))

    b = baseline_metrics  # alias

    # ─────────────────────────────────────────────────────────────────────
    # IN BẢNG ĐỐI SÁNH TOÁN HỌC
    # ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("   BẢNG ĐỐI SÁNH HIỆU NĂNG: BASELINE vs SOLVER (IAP)")
    print("=" * 70)

    W = 18  # column width

    def row(label, b_val, s_val, unit="", fmt="{:.0f}", improve_lower=True):
        bv = fmt.format(b_val)
        sv = fmt.format(s_val)
        if improve_lower:
            delta = b_val - s_val
            symbol = "▲" if delta > 0 else ("▼" if delta < 0 else "─")
            sign = "+" if delta > 0 else ""
        else:
            delta = s_val - b_val
            symbol = "▲" if delta > 0 else ("▼" if delta < 0 else "─")
            sign = "+" if delta > 0 else ""
        delta_str = f"{sign}{fmt.format(abs(delta))}{unit} {symbol}"
        print(f"  {label:<28} {bv+unit:>{W}} {sv+unit:>{W}} {delta_str:>20}")

    header = f"  {'Tiêu chí':<28} {'Baseline':>{W}} {'Solver':>{W}} {'Cải thiện':>20}"
    sep    = "  " + "-" * 68
    print(header)
    print(sep)

    print("  [NHÓM VI PHẠM RÀNG BUỘC]")
    row("M6 – Thiếu nhân sự (vị trí)",  b['slack_cap'],   solver_slack_cap)
    row("     Điểm phạt M6",            b['M6_penalty_cap'], solver_M6, fmt="{:,.0f}")
    row("M7 – Ép người bận (lần)",      b['slack_busy'],  solver_slack_busy)
    row("     Điểm phạt M7",            b['M7_penalty_busy'], solver_M7, fmt="{:,.0f}")
    row("M8 – Sai chuyên môn (lần)",    b['slack_qual'],  solver_slack_qual)
    row("     Điểm phạt M8",            b['M8_penalty_qual'], solver_M8, fmt="{:,.0f}")

    print(sep)
    print("  [NHÓM CHẤT LƯỢNG LỊCH]")
    row("M2 – Fairness Gap (ca)",       b['gap'],         solver_gap)
    row("     W_high",                  b['w_high'],      solver_w_high)
    row("     W_low",                   b['w_low'],       solver_w_low)
    row("M3 – Phạt tĩnh (nguyện vọng)", b['M3_static_penalty'], s_m3, fmt="{:.1f}")
    row("M4 – Phạt mệt mỏi",           b['M4_fatigue_penalty'], s_m4, fmt="{:.1f}")
    row("M5 – Phạt di chuyển",         b['M5_travel_penalty'],  s_m5, fmt="{:.1f}")
    row("M1 – Tổng phạt chất lượng",   b['M1_total_quality'],   s_m3 + s_m4 + s_m5, fmt="{:,.1f}")

    print(sep)
    print("  [ĐẾM VI PHẠM PHỤ]")
    row("  Số ca mệt mỏi (>2/ngày)",   b['fatigue_count'],  solver_fatigue_cnt)
    row("  Số ca di chuyển/chờ",       b['travel_count'],   solver_travel_cnt)

    print(sep)
    print("  [HÀM MỤC TIÊU TỔNG THỂ]")
    row("  OBJECTIVE (thấp hơn = tốt)", b['objective'], solver_objective, fmt="{:,.1f}")

    # Tính % cải thiện
    if b['objective'] > 0:
        pct = (b['objective'] - solver_objective) / b['objective'] * 100
        pct_str = f"{pct:+.1f}%"
    else:
        pct_str = "N/A"
    print(f"\n  ► Cải thiện hàm mục tiêu: {pct_str}")
    print("=" * 70)


# PHẦN 4: HÀM TIỆN ÍCH — CHẠY TOÀN BỘ PIPELINE PHÂN TÍCH


def run_analysis_pipeline(file_excel: str, data_model: dict, weights: dict = None):
    """
    Hàm wrapper — gọi từ main.py sau khi Solver xuất xong solver_metrics.json.

    Quy trình:
    1. Đọc solver_metrics.json
    2. Gọi compute_baseline_metrics() với dữ liệu từ data_model (đã có cache)
    3. Gọi generate_dashboard_and_plots()

    Parameters
    ----------
    file_excel  : Đường dẫn file Excel gốc
    data_model  : Dict trả về bởi preprocess_data() (đã tích hợp JSON cache)
    weights     : Trọng số phạt (tuỳ chọn)
    """
    print("\n" + "=" * 60)
    print("   PHÂN TÍCH HIỆU NĂNG: BASELINE vs SOLVER")
    print("=" * 60)

    output_dir = _get_cache_dir()
    solver_metrics = load_solver_metrics(output_dir)

    if not solver_metrics:
        print("⚠️  Chưa tìm thấy solver_metrics.json.")
        print("   Vui lòng chạy Solver và lưu kết quả trước khi phân tích.")
        return

    baseline = compute_baseline_metrics(
        file_excel=file_excel,
        B_ij=data_model['parameters']['B_ij'],
        Campus_like_ik=data_model['synthetic']['Campus_like_ik'],
        L_i=data_model['synthetic']['L_i'],
        CT_info=data_model['parameters']['CT_info'],
        weights=weights
    )

    generate_dashboard_and_plots(baseline, solver_metrics, weights=weights, output_dir=output_dir)

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    file_excel = os.path.join(project_root, 'input', 'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx')
    from data_preprocessing import preprocess_data
    data_model = preprocess_data(file_excel)
    
    # 3. Khởi chạy pipeline phân tích, tính toán baseline
    run_analysis_pipeline(file_excel, data_model, weights=None)
