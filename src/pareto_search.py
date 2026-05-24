"""
pareto_search.py — Pareto Frontier Explorer cho IAP Solver
===========================================================
Mục đích:
  Tự động quét lưới các giá trị theta (và tùy chọn omega) để tìm
  tập tối ưu Pareto giữa hai mục tiêu xung đột:
    - F1: Công bằng (Fairness) — đo bằng W_high - W_low (gap ca)
    - F2: Chất lượng lịch (Penalty) — đo bằng tổng vi phạm ràng buộc mềm

Cách dùng:
  python pareto_search.py                  # Chạy với config mặc định
  python pareto_search.py --quick          # Chế độ nhanh (ít điểm hơn)
  python pareto_search.py --theta 100,500,1000,2000,5000
  python pareto_search.py --csv output.csv # Chỉ định file CSV đầu ra

Đầu ra:
  - output/pareto_results.csv  : Bảng kết quả đầy đủ mọi điểm
  - output/pareto_summary.txt  : Tóm tắt + điểm Pareto được đề xuất
  - stdout: Progress bar + bảng so sánh trực tiếp

Thuật toán:
  1. Chuẩn hóa F1, F2 về [0,1]
  2. Lọc các điểm Pareto-dominated (điểm bị thống trị bởi điểm khác)
  3. Tính "balance score" = sqrt(F1_norm^2 + F2_norm^2) để tìm knee point
  4. Đề xuất điểm có balance score nhỏ nhất làm hệ số tối ưu
"""

import os
import sys
import csv
import time
import argparse
import itertools
from pathlib import Path

# ---------------------------------------------------------------------------
# Thêm thư mục src vào sys.path để import được các module của dự án
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))
else:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from data_preprocessing import preprocess_data, audit_static_feasibility
    from model_builder import build_model
    from solver import solve_model
except ImportError as e:
    print(f"❌ Không thể import module: {e}")
    print("   Đảm bảo pareto_search.py nằm cùng thư mục với src/ hoặc các file .py")
    sys.exit(1)


# ===========================================================================
# CẤU HÌNH LƯỚI QUÉT (GRID CONFIG)
# ===========================================================================

DEFAULT_THETA_GRID = [20, 40, 60, 80, 100, 200, 500, 1000, 10000]
"""
Giải thích ý nghĩa từng mức theta:
  20     → Mặc định ban đầu, hầu như không quan tâm công bằng
  100    → Bắt đầu có ưu tiên nhẹ cho công bằng
  500    → Cân bằng tốt (điểm thường được chọn trong thực tế)
  1000   → Thiên về công bằng
  2000   → Rất thiên về công bằng, có thể gây vi phạm soft-constraint
  5000   → Cực đoan, công bằng gần tuyệt đối
  10000  → Ngưỡng nguy hiểm, dễ gây Infeasible hoặc timeout
"""

DEFAULT_OMEGA_GRID = [1.0]
"""
Mặc định cố định omega=1.0 và chỉ biến thiên theta.
Để grid search 2D (cả omega lẫn theta), bạn có thể mở rộng:
  DEFAULT_OMEGA_GRID = [0.5, 1.0, 2.0, 5.0]
"""

QUICK_THETA_GRID = [20, 200, 500, 2000, 5000]
"""Chế độ nhanh: ít điểm hơn, phù hợp để test nhanh"""

DEFAULT_TAX_WEIGHTS = {
    'TAX_LACK_STAFF': 10000.0,
    'TAX_FORCE_BUSY': 5000.0,
    'TAX_BAD_QUAL':   5000.0,
}
"""
Các trọng số TAX được cố định trong quá trình Pareto search.
Bạn có thể thay đổi chúng nếu muốn khám phá thêm chiều không gian.
"""


# ===========================================================================
# HÀM TIỆN ÍCH
# ===========================================================================

def print_separator(char="─", width=65):
    print(char * width)

def print_progress(current, total, label="", width=40):
    """In thanh tiến trình ASCII đơn giản"""
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = 100 * current / total
    print(f"\r  [{bar}] {pct:5.1f}%  {label:<30}", end="", flush=True)

def format_duration(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


# ===========================================================================
# BỘ LỌC PARETO (PARETO DOMINANCE FILTER)
# ===========================================================================

def is_dominated(point, candidates):
    """
    Kiểm tra xem `point` có bị thống trị (dominated) bởi bất kỳ điểm nào
    trong `candidates` không.
    
    Điểm A thống trị điểm B nếu:
      - A tốt hơn hoặc bằng B trên MỌI tiêu chí
      - A tốt hơn B trên ÍT NHẤT MỘT tiêu chí
    
    Ở đây: tiêu chí là (gap, total_violations) — cả hai đều minimize.
    """
    g0, v0 = point['gap'], point['total_violations']
    for c in candidates:
        if c is point:
            continue
        gc, vc = c['gap'], c['total_violations']
        if gc <= g0 and vc <= v0 and (gc < g0 or vc < v0):
            return True
    return False

def find_pareto_frontier(results):
    """
    Lọc và trả về tập các điểm Pareto-optimal từ danh sách kết quả.
    Chỉ xét các điểm có status là Optimal/Near-Optimal/Feasible.
    """
    valid = [r for r in results if r['status'] in ('Optimal', 'Near-Optimal', 'Feasible')
             and r['gap'] is not None]
    
    pareto = [p for p in valid if not is_dominated(p, valid)]
    pareto.sort(key=lambda p: p['gap'])
    return pareto

def normalize_and_score(pareto_points):
    """
    Chuẩn hóa F1 (gap) và F2 (violations) về [0,1],
    tính balance score = khoảng cách Euclid từ gốc (0,0) trong không gian chuẩn hóa.
    Điểm có score nhỏ nhất = "knee point" = điểm cân bằng tốt nhất.
    """
    if not pareto_points:
        return pareto_points
    
    gaps  = [p['gap'] for p in pareto_points]
    viols = [p['total_violations'] for p in pareto_points]
    
    g_min, g_max = min(gaps), max(gaps)
    v_min, v_max = min(viols), max(viols)
    
    g_range = g_max - g_min if g_max != g_min else 1
    v_range = v_max - v_min if v_max != v_min else 1
    
    for p in pareto_points:
        g_norm = (p['gap'] - g_min) / g_range
        v_norm = (p['total_violations'] - v_min) / v_range
        p['balance_score'] = (g_norm**2 + v_norm**2) ** 0.5
        p['g_norm'] = g_norm
        p['v_norm'] = v_norm
    
    return pareto_points


# ===========================================================================
# HÀM CHÍNH: CHẠY MỘT ĐIỂM TRONG LƯỚI
# ===========================================================================

def run_single_point(data_model, omega, theta, tax_weights):
    """
    Chạy solver cho một cặp (omega, theta) và trả về dict kết quả.
    Bắt mọi exception để grid search không bị gián đoạn.
    """
    weights = {
        'omega': omega,
        'theta': theta,
        **tax_weights
    }
    
    result = {
        'omega': omega,
        'theta': theta,
        'status': 'Error',
        'obj_value': None,
        'solve_time': None,
        'gap': None,
        'high': None,
        'low': None,
        'slack_cap': 0,
        'slack_busy': 0,
        'slack_qual': 0,
        'fatigue_count': 0,
        'travel_count': 0,
        'total_violations': None,
        'balance_score': None,
        'error_msg': None,
    }
    
    try:
        prob, X = build_model(data_model, weights=weights)
        status, metrics = solve_model(prob, X, data_model, skip_export=True)
        
        result.update({
            'status':       status,
            'obj_value':    metrics.get('obj_value'),
            'solve_time':   metrics.get('solve_time'),
            'gap':          metrics.get('gap', 0) or 0,
            'high':         metrics.get('high'),
            'low':          metrics.get('low'),
            'slack_cap':    metrics.get('slack_cap', 0),
            'slack_busy':   metrics.get('slack_busy', 0),
            'slack_qual':   metrics.get('slack_qual', 0),
            'fatigue_count':metrics.get('fatigue_count', 0),
            'travel_count': metrics.get('travel_count', 0),
        })
        
        # Tổng vi phạm = trọng số có ý nghĩa kinh doanh:
        # slack_cap được tính nặng hơn vì thiếu người gác là lỗi nghiêm trọng nhất
        result['total_violations'] = (
            result['slack_cap']   * 3 +   # Thiếu người: nghiêm trọng nhất
            result['slack_busy']  * 1 +   # Ép người bận: trung bình
            result['slack_qual']  * 2 +   # Sai chuyên môn: khá nghiêm trọng
            result['fatigue_count']* 1 +  # Mệt mỏi (ca liền nhau) 
            result['travel_count'] * 1    # Đi lại xa giữa các cơ sở s
        )
        
    except Exception as e:
        result['error_msg'] = str(e)
    
    return result


# ===========================================================================
# XUẤT KẾT QUẢ
# ===========================================================================

def save_csv(results, output_path):
    """Lưu toàn bộ kết quả ra CSV"""
    if not results:
        return
    
    fieldnames = [
        'omega', 'theta', 'status', 'obj_value', 'solve_time',
        'gap', 'high', 'low',
        'slack_cap', 'slack_busy', 'slack_qual',
        'fatigue_count', 'travel_count', 'total_violations',
        'balance_score', 'error_msg'
    ]
    
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\n✓ Đã lưu CSV: {output_path}")

def print_results_table(results, pareto_points, recommended):
    print_separator("═")
    print("   KẾT QUẢ GRID SEARCH — PARETO FRONTIER")
    print_separator("═")
    
    print(f"\n{'θ':>8} {'Status':<14} {'Gap(ca)':>8} {'Violations':>12} "
          f"{'SolveTime':>10} {'Pareto':>7} {'Recommend':>10}")
    print_separator()
    
    pareto_thetas = {p['theta'] for p in pareto_points}
    rec_theta = recommended['theta'] if recommended else None
    
    for r in results:
        if r['status'] == 'Error':
            print(f"  θ={r['theta']:>6}  ❌ ERROR: {r['error_msg'][:35]}")
            continue
        
        is_pareto = r['theta'] in pareto_thetas
        is_rec    = r['theta'] == rec_theta
        
        gap_str   = f"{r['gap']:.1f}" if r['gap'] is not None else "N/A"
        viol_str  = f"{r['total_violations']:.0f}" if r['total_violations'] is not None else "N/A"
        time_str  = format_duration(r['solve_time']) if r['solve_time'] else "N/A"
        pareto_str = "✓" if is_pareto else ""
        rec_str    = "★ TỐI ƯU" if is_rec else ""
        
        status_icon = {"Optimal": "🟢", "Near-Optimal": "🟡", 
                       "Feasible": "🟠", "Infeasible": "🔴"}.get(r['status'], "⚪")
        
        print(f"  θ={r['theta']:>6}  {status_icon} {r['status']:<12}  "
              f"{gap_str:>7}  {viol_str:>12}  {time_str:>10}  "
              f"{pareto_str:>7}  {rec_str:>10}")
    
    print_separator()

def save_summary(results, pareto_points, recommended, output_path):
    """Lưu tóm tắt ra file text"""
    lines = []
    lines.append("=" * 65)
    lines.append("   PARETO SEARCH SUMMARY — IAP SOLVER")
    lines.append("=" * 65)
    lines.append(f"Tổng số điểm đã chạy : {len(results)}")
    lines.append(f"Điểm Pareto-optimal  : {len(pareto_points)}")
    lines.append("")
    
    if recommended:
        lines.append("★ ĐIỂM ĐƯỢC ĐỀ XUẤT (Knee Point):")
        lines.append(f"   omega = {recommended['omega']}")
        lines.append(f"   theta = {recommended['theta']}")
        lines.append(f"   Gap ca thi : {recommended['gap']:.1f} "
                     f"(Max={recommended['high']}, Min={recommended['low']})")
        lines.append(f"   Vi phạm    : {recommended['total_violations']:.0f}")
        lines.append(f"   Status     : {recommended['status']}")
        lines.append(f"   Giải thích : Đây là điểm cân bằng tốt nhất giữa công bằng")
        lines.append(f"                và chất lượng lịch (balance_score tối thiểu).")
    else:
        lines.append("⚠ Không tìm được điểm Pareto-optimal nào.")
    
    lines.append("")
    lines.append("TẬP PARETO ĐẦY ĐỦ (sắp xếp theo Gap tăng dần):")
    lines.append(f"{'θ':>8}  {'Gap':>6}  {'Violations':>12}  {'Balance':>8}  Status")
    lines.append("-" * 55)
    for p in pareto_points:
        bs = f"{p['balance_score']:.4f}" if p.get('balance_score') is not None else "N/A"
        marker = " ← ĐỀ XUẤT" if recommended and p['theta'] == recommended['theta'] else ""
        lines.append(f"  θ={p['theta']:>6}  {p['gap']:>6.1f}  "
                     f"{p['total_violations']:>12.0f}  {bs:>8}  {p['status']}{marker}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    
    print(f"✓ Đã lưu tóm tắt: {output_path}")


# ===========================================================================
# ENTRY POINT
# ===========================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Pareto Grid Search cho IAP Solver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--quick', action='store_true',
                        help='Chế độ nhanh (5 điểm thay vì 8)')
    parser.add_argument('--theta', type=str, default=None,
                        help='Danh sách theta cách nhau bởi dấu phẩy, VD: 20,500,2000')
    parser.add_argument('--omega', type=str, default=None,
                        help='Danh sách omega, VD: 0.5,1.0,2.0')
    parser.add_argument('--csv', type=str, default=None,
                        help='Đường dẫn file CSV đầu ra')
    parser.add_argument('--input', type=str, default=None,
                        help='Đường dẫn file Excel đầu vào (ghi đè đường dẫn mặc định)')
    return parser.parse_args()


def main():
    args = parse_args()
    
    # --- Xác định lưới quét ---
    if args.theta:
        try:
            theta_grid = [float(x.strip()) for x in args.theta.split(',')]
        except ValueError:
            print("❌ Lỗi: --theta phải là danh sách số, VD: 20,500,2000")
            sys.exit(1)
    elif args.quick:
        theta_grid = QUICK_THETA_GRID
    else:
        theta_grid = DEFAULT_THETA_GRID
    
    omega_grid = [float(x.strip()) for x in args.omega.split(',')] if args.omega else DEFAULT_OMEGA_GRID
    
    all_combinations = list(itertools.product(omega_grid, theta_grid))
    total_runs = len(all_combinations)
    
    # --- Xác định file đầu vào ---
    if args.input:
        file_excel = args.input
    else:
        script_dir = Path(__file__).resolve().parent
        project_root = script_dir.parent
        file_excel = project_root / 'input' / 'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx'
    
    if not Path(file_excel).exists():
        print(f"❌ Không tìm thấy file: {file_excel}")
        sys.exit(1)
    
    # --- Xác định đường dẫn đầu ra ---
    project_root_for_output = Path(file_excel).resolve().parent.parent
    output_dir = project_root_for_output / 'output'
    output_dir.mkdir(exist_ok=True)
    
    csv_path     = Path(args.csv) if args.csv else output_dir / 'pareto_results.csv'
    summary_path = output_dir / 'pareto_summary.txt'
    
    # --- Banner ---
    print_separator("═")
    print("   PARETO FRONTIER EXPLORER — IAP SOLVER")
    print_separator("═")
    print(f"  Theta grid  : {theta_grid}")
    print(f"  Omega grid  : {omega_grid}")
    print(f"  Tổng số run : {total_runs}")
    print(f"  File đầu vào: {file_excel}")
    print_separator()
    
    # --- Load và audit dữ liệu một lần duy nhất ---
    print("\n[1/3] Đang tải và kiểm tra dữ liệu...")
    try:
        data_model = preprocess_data(str(file_excel))
        is_feasible, audit_errors = audit_static_feasibility(data_model)
        if not is_feasible:
            print(f"❌ Dữ liệu không khả thi tĩnh ({len(audit_errors)} lỗi). Dừng lại.")
            for err in audit_errors[:5]:
                print(f"   - {err}")
            sys.exit(1)
        print("   ✓ Dữ liệu hợp lệ.")
    except Exception as e:
        print(f"❌ Lỗi khi tải dữ liệu: {e}")
        sys.exit(1)
    
    # --- Chạy Grid Search ---
    print(f"\n[2/3] Đang chạy Grid Search ({total_runs} điểm)...")
    print_separator()
    
    results = []
    search_start = time.time()
    
    for idx, (omega, theta) in enumerate(all_combinations):
        label = f"θ={theta}, ω={omega}"
        print_progress(idx, total_runs, label)
        
        point_result = run_single_point(data_model, omega, theta, DEFAULT_TAX_WEIGHTS)
        results.append(point_result)
        
        # In nhanh kết quả sau mỗi run
        st = point_result['status']
        gap_str = f"gap={point_result['gap']:.1f}" if point_result['gap'] is not None else "gap=N/A"
        icons = {"Optimal": "✅", "Near-Optimal": "🟡", "Feasible": "🟠",
                 "Infeasible": "❌", "Error": "💥"}
        icon = icons.get(st, "?")
        print(f"\r  {icon} θ={theta:>6}, ω={omega} → {st:<14}  {gap_str}")
    
    total_time = time.time() - search_start
    print(f"\n  ✓ Hoàn tất trong {format_duration(total_time)}")
    
    # --- Phân tích Pareto ---
    print("\n[3/3] Đang phân tích Pareto Frontier...")
    pareto_points = find_pareto_frontier(results)
    pareto_points = normalize_and_score(pareto_points)
    
    recommended = None
    if pareto_points:
        # Knee point = điểm có balance_score nhỏ nhất
        recommended = min(pareto_points, key=lambda p: p.get('balance_score', float('inf')))
    
    # --- In bảng kết quả ---
    print_results_table(results, pareto_points, recommended)
    
    # --- Kết luận ---
    if recommended:
        print(f"\n★ ĐỀ XUẤT: Sử dụng  omega={recommended['omega']},  theta={recommended['theta']}")
        print(f"   → Gap ca   : {recommended['gap']:.1f}  "
              f"(Max={recommended['high']}, Min={recommended['low']})")
        print(f"   → Vi phạm  : {recommended['total_violations']:.0f}")
        print(f"   → Lý do    : Điểm cân bằng Pareto tốt nhất (balance_score tối thiểu)")
    
    # --- Lưu kết quả ---
    save_csv(results, csv_path)
    save_summary(results, pareto_points, recommended, summary_path)
    
    print_separator("═")
    print("   HOÀN THÀNH")
    print_separator("═")
    
    return results, pareto_points, recommended


if __name__ == "__main__":
    main()