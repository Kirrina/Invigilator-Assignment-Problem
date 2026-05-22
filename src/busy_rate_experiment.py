"""
busy_rate_experiment.py
=======================
Thí nghiệm đo ngưỡng tới hạn (critical threshold) của busy_rate.

MỤC TIÊU:
  - Chạy lần lượt các mức busy_rate tăng dần
  - Ghi nhận trạng thái Optimal / Infeasible cho từng lần lặp
  - Tìm ngưỡng mà model bắt đầu Infeasible
  - Xuất bảng kết quả ra terminal 

CÁCH CHẠY:
  python busy_rate_experiment.py
"""

import os
import sys
import time
import threading

# ─── CẤU HÌNH THÍ NGHIỆM ────────────────────────────────────────────────────

current_dir  = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
FILE_EXCEL   = os.path.join(project_root, 'input',
               'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx')

BUSY_RATES = [0.05, 0.4, 0.8, 1.0]
NUM_TRIALS = 1

# Timeout riêng cho thí nghiệm (giây) — độc lập với timeLimit trong solver.py
# Mỗi trial CBC sẽ bị dừng sau tối đa SOLVER_TIMEOUT giây.
# solver.py có timeLimit=60; giá trị này ghi đè khi gọi từ experiment.
SOLVER_TIMEOUT = 5  # giây — đủ để CBC tìm được lời giải trên full dataset

WEIGHTS = {
    'omega': 1.0, 'theta': 20.0,
    'TAX_LACK_STAFF': 10000.0, 'TAX_FORCE_BUSY': 5000.0, 'TAX_BAD_QUAL': 5000.0
}

OUTPUT_CSV = os.path.join(current_dir, 'busy_rate_results.csv')

# ─────────────────────────────────────────────────────────────────────────────


class LiveTimer:
    """
    In đồng hồ đếm giây ngay trên cùng một dòng terminal trong khi CBC đang chạy.
    Dừng khi gọi .stop().
    """
    def __init__(self, prefix="  ⏱  Solver đang chạy"):
        self.prefix  = prefix
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._tick, daemon=True)

    def start(self):
        self._t0 = time.time()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)
        # Xóa dòng timer, in newline sạch
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()

    def _tick(self):
        while not self._stop.is_set():
            elapsed = time.time() - self._t0
            sys.stdout.write(f"\r{self.prefix}: {elapsed:6.1f}s ...")
            sys.stdout.flush()
            time.sleep(0.5)


def _fmt_eta(seconds):
    """Chuyển số giây thành chuỗi mm:ss dễ đọc."""
    if seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _progress_header(total_trials):
    print(f"\n{'═'*65}")
    print(f"  THÍ NGHIỆM: NGƯỠNG TỚI HẠN CỦA BUSY_RATE  (CBC SOLVER)")
    print(f"{'═'*65}")
    print(f"  Số mức busy_rate : {len(BUSY_RATES)}  ({BUSY_RATES[0]:.0%} → {BUSY_RATES[-1]:.0%})")
    print(f"  Số lần lặp / mức : {NUM_TRIALS}")
    print(f"  Tổng số trial    : {total_trials}")
    print(f"  Timeout / trial  : {SOLVER_TIMEOUT}s")
    print(f"{'═'*65}\n")


def run_experiment():
    # ── Kiểm tra file đầu vào ────────────────────────────────────────
    if not os.path.exists(FILE_EXCEL):
        print(f"❌ Không tìm thấy: {FILE_EXCEL}")
        sys.exit(1)

    try:
        from data_preprocessing import preprocess_data
    except ImportError:
        print("❌ Không tìm thấy data_preprocessing_v2.py!")
        sys.exit(1)

    try:
        from model_builder import build_model
        import pulp
    except ImportError as e:
        print(f"❌ Import lỗi: {e}")
        sys.exit(1)

    total_trials = len(BUSY_RATES) * NUM_TRIALS
    _progress_header(total_trials)

    all_results        = []
    summary            = []
    completed_trials   = 0
    total_solve_so_far = 0.0   # tổng thời gian solver đã tiêu tốn
    critical_threshold = None
    exp_start          = time.time()

    for rate_idx, rate in enumerate(BUSY_RATES):
        rate_pct       = f"{rate:.0%}"
        trial_statuses = []
        trial_times    = []

        # ── Tiêu đề mức busy_rate ────────────────────────────────────
        print(f"{'─'*65}")
        print(f"  [{rate_idx+1}/{len(BUSY_RATES)}] busy_rate = {rate_pct}  "
              f"(đã hoàn thành {completed_trials}/{total_trials} trial)")
        print(f"{'─'*65}")

        for trial in range(1, NUM_TRIALS + 1):
            # Ước tính ETA
            remaining_trials = total_trials - completed_trials
            if completed_trials > 0:
                avg_t = total_solve_so_far / completed_trials
                eta   = _fmt_eta(avg_t * remaining_trials)
            else:
                eta = "--:--"

            print(f"\n  Trial {trial}/{NUM_TRIALS}  |  "
                  f"Tiến độ: {completed_trials}/{total_trials}  |  "
                  f"ETA: {eta}")

            # Seed khác nhau mỗi trial để B_ij không trùng
            import numpy as np, random as py_random
            np.random.seed(42 + trial)
            py_random.seed(42 + trial)

            
            try:
                # 1. Tiền xử lý
                print(f"     → Đang load & preprocess dữ liệu...")
                # Trong busy_rate_experiment.py, trước khi gọi preprocess_data:
                import shutil
                cache_path = os.path.join(project_root, 'output', 'B_ij_cache.json')
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                
                campus_cache_path = os.path.join(project_root, 'output', 'Campus_like_cache.json')
                if os.path.exists(campus_cache_path):
                    os.remove(campus_cache_path)
                data_model = preprocess_data(FILE_EXCEL, soft_busy_rate=0.05, hard_busy_rate=rate)
                                #data_model = preprocess_data(FILE_EXCEL, busy_rate=rate)

                # 2. Build model
                print(f"     → Đang xây dựng mô hình ILP...")
                prob, X = build_model(data_model, weights=WEIGHTS)

                # 3. Solve với timeout riêng của thí nghiệm
                print(f"     → Solver CBC đang chạy (timeout={SOLVER_TIMEOUT}s)...")
                timer = LiveTimer(prefix="       ⏱  CBC")
                timer.start()

                t0     = time.time()
                status = prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=SOLVER_TIMEOUT))
                t_end  = time.time()

                timer.stop()

                status_str = pulp.LpStatus[status]
                solve_time = round(t_end - t0, 3)
                icon       = "✅" if status_str == "Optimal" else "❌"

                print(f"     {icon} {status_str}  |  Thời gian: {solve_time:.2f}s")

            except Exception as e:
                if 'timer' in locals():
                    timer.stop()
                print(f"     ⚠️  LỖI: {e}")
                status_str = "ERROR"
                solve_time = 0.0

            # ── Ghi kết quả ──────────────────────────────────────────
            all_results.append({
                'busy_rate'    : rate,
                'busy_rate_pct': rate_pct,
                'trial'        : trial,
                'status'       : status_str,
                'solve_time'   : solve_time,
            })
            trial_statuses.append(status_str)
            trial_times.append(solve_time)

            completed_trials   += 1
            total_solve_so_far += solve_time

        # ── Tổng hợp mức này ─────────────────────────────────────────
        n_optimal    = trial_statuses.count("Optimal")
        n_infeasible = sum(1 for s in trial_statuses if s != "Optimal")
        feasible_pct = n_optimal / NUM_TRIALS * 100
        avg_time     = sum(trial_times) / len(trial_times) if trial_times else 0

        summary.append({
            'busy_rate'    : rate,
            'busy_rate_pct': rate_pct,
            'n_trials'     : NUM_TRIALS,
            'n_optimal'    : n_optimal,
            'n_infeasible' : n_infeasible,
            'feasible_pct' : round(feasible_pct, 1),
            'avg_time_s'   : round(avg_time, 2),
        })

        bar  = "█" * n_optimal + "░" * n_infeasible
        print(f"\n  📊  {rate_pct}: {n_optimal}/{NUM_TRIALS} Optimal  "
              f"[{bar}]  ({feasible_pct:.0f}%)  avg={avg_time:.1f}s")

        if critical_threshold is None and n_optimal < NUM_TRIALS:
            critical_threshold = rate
            print(f"  ⚠️   → NGƯỠNG TỚI HẠN phát hiện tại busy_rate = {rate_pct}!")

    # ── Bảng tổng hợp cuối ───────────────────────────────────────────
    total_elapsed = time.time() - exp_start
    print(f"\n\n{'═'*65}")
    print(f"       BẢNG TỔNG HỢP KẾT QUẢ THÍ NGHIỆM BUSY_RATE")
    print(f"{'═'*65}")
    print(f"  {'Busy Rate':<10} | {'Optimal':<8} | {'Infeasible':<11} | {'Feasible%':<10} | {'Avg Time'}")
    print(f"  {'-'*58}")
    for row in summary:
        bar = "█" * row['n_optimal'] + "░" * row['n_infeasible']
        print(f"  {row['busy_rate_pct']:<10} | "
              f"{row['n_optimal']:<8} | "
              f"{row['n_infeasible']:<11} | "
              f"{row['feasible_pct']:>6.1f}%  {bar:<4} | "
              f"{row['avg_time_s']:.2f}s")
    print(f"{'═'*65}")
    print(f"  Tổng thời gian thí nghiệm: {_fmt_eta(total_elapsed)}")

    if critical_threshold is not None:
        print(f"\n  🎯 NGƯỠNG TỚI HẠN: busy_rate = {critical_threshold:.0%}")
        print(f"     → Đây là giá trị đưa vào phần phân tích báo cáo.")
    else:
        print(f"\n  ✅ Tất cả mức đều Optimal. Cân nhắc thử mức cao hơn 50%.")

    return all_results, summary


if __name__ == "__main__":
    print("\n" + "═"*65)
    print("   BUSY RATE EXPERIMENT — IAP PROJECT")
    print("═"*65)
    run_experiment()
    print("\n" + "═"*65)
    print("  ✓ Thí nghiệm hoàn tất!")
    print("═"*65 + "\n")