import pandas as pd
import numpy as np
import random
import os

def convert_time_to_float(time_str):
    """
    Convert Vietnamese time format to float hours.
    
    Handles multiple formats:
    - "9g30" or "9giờ30" (Vietnamese format)
    - "9 giờ 30" (Vietnamese format with spaces)
    - "9:30" (Colon format)
    - "14.5" (Float format)
    - "9 30" (Space-separated)
    
    Args:
        time_str: Time string in any of the above formats
        
    Returns:
        float: Hours as decimal (e.g., 9.5 for 9 hours 30 minutes)
        
    Raises:
        ValueError: If time format is invalid or values out of range
    """
    # Handle None and NaN values
    if time_str is None or (isinstance(time_str, float) and pd.isna(time_str)):
        raise ValueError("Time value is None or NaN")
    
    time_str = str(time_str).lower().strip()
    
    # Remove Vietnamese words and normalize separators
    time_str = time_str.replace('giờ', '').replace('phút', '').replace(':', ' ').replace('g', ' ')
    time_str = ' '.join(time_str.split())  # Normalize whitespace
    
    try:
        parts = time_str.split()
        
        if len(parts) == 0:
            raise ValueError(f"Empty time string")
        
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        
        # Validate ranges
        if not (0 <= h <= 23):
            raise ValueError(f"Hour {h} out of range [0-23]")
        if not (0 <= m <= 59):
            raise ValueError(f"Minute {m} out of range [0-59]")
        
        return h + m / 60.0
    
    except (ValueError, IndexError) as e:
        raise ValueError(f"Cannot parse time '{time_str}': {str(e)}")

def normalize_role(role):
    role = role.strip().lower()

    mapping = {
        'cbct': 'CBCT',
        'thư ký': 'Thuky',
        'trưởng hđ': 'TruongHD'
    }

    return mapping.get(role, role)

def preprocess_data(file_path):
    """
    Preprocess Excel data and extract model parameters.

    Validates:
    - File exists and is readable
    - Required columns present
    - Data types are correct
    - Data is not empty
    - Time and duration formats valid

    Args:
        file_path: Path to Excel file

    Returns:
        dict: Data model with sets, parameters, and synthetic data

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If data validation fails
    """
    print(f"Đang đọc dữ liệu từ: {file_path}")

    # Validate file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")

    df = pd.read_excel(file_path)

    # Validate required columns exist
    required_columns = ['MS của CÁN BỘ COI THI', 'MS Ca thi', 'Ngày', 'GIỜ', 'Thời gian', 'Cơ sở', 'Nhiệm vụ']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        print(f"❌ Missing required columns: {missing}")
        print(f"Available columns: {list(df.columns)}")
        raise ValueError(f"Missing required columns: {missing}")

    # --- FIX: Fill missing Campus using 'Nhiệm vụ' hint ---
    def extract_campus(row):
        campus = row['Cơ sở']
        if pd.isna(campus) or str(campus).strip() == '':
            task = str(row['Nhiệm vụ'])
            if '_' in task:
                campus_code = task.split('_')[0]
                # User hint: LTK -> Cơ sở 1, DiAn -> Cơ sở 2
                if campus_code == 'LTK': return 'Cơ sở 1'
                if campus_code == 'DiAn': return 'Cơ sở 2'
                return campus_code
            return "Unknown"
        return str(campus).strip()

    df['Cơ sở'] = df.apply(extract_campus, axis=1)

    # --- FIX: Create Unique Shift ID to avoid collisions across campuses ---
    # We use a pipe '|' as a separator to make it easy to split later
    df['Unique_Shift_ID'] = df['MS Ca thi'].astype(str) + "|" + df['Cơ sở']

    CB = df['MS của CÁN BỘ COI THI'].dropna().unique().tolist()
    CT = df['Unique_Shift_ID'].dropna().unique().tolist()
    K = df['Cơ sở'].dropna().unique().tolist()

    # Validate not empty
    if not CB or not CT or not K:
        print(f"❌ ERROR: Empty data extracted")
        print(f"   Staff (CB): {len(CB)} items")
        print(f"   Shifts (CT): {len(CT)} items")
        print(f"   Campuses (K): {len(K)} items")
        raise ValueError("No valid data extracted from Excel")

    df['Vai_tro'] = (df['Nhiệm vụ'].astype(str).apply(lambda x: normalize_role(x.split('_')[-1])))
    R = df['Vai_tro'].unique().tolist()

    if not R:
        raise ValueError("No roles found after normalization")

    CT_info = {}
    shift_metadata = df[['Unique_Shift_ID', 'MS Ca thi', 'Ngày', 'GIỜ', 'Thời gian', 'Cơ sở']].drop_duplicates()

    for idx, row in shift_metadata.iterrows():
        try:
            sid_unique = row['Unique_Shift_ID']
            sid_original = row['MS Ca thi']

            # Validate shift ID
            if pd.isna(sid_original):
                print(f"⚠️  Skipping row {idx}: Missing shift ID")
                continue

            # Parse time with validation
            try:
                start_t = convert_time_to_float(row['GIỜ'])
            except ValueError as e:
                raise ValueError(f"Row {idx}, Shift {sid_original}: {str(e)}")

            # Parse and validate duration
            duration_raw = row['Thời gian']
            if pd.isna(duration_raw):
                raise ValueError(f"Row {idx}, Shift {sid_original}: Missing duration")

            try:
                duration_minutes = float(duration_raw)
            except (ValueError, TypeError):
                raise ValueError(f"Row {idx}, Shift {sid_original}: Invalid duration '{duration_raw}' (must be numeric)")

            if duration_minutes <= 0:
                raise ValueError(f"Row {idx}, Shift {sid_original}: Duration must be > 0, got {duration_minutes}")

            # Parse and validate date
            try:
                pure_date = pd.to_datetime(row['Ngày']).date()
            except (ValueError, TypeError):
                raise ValueError(f"Row {idx}, Shift {sid_original}: Invalid date '{row['Ngày']}'")

            # Campus already extracted and validated above
            campus = row['Cơ sở']

            # Calculate end time
            duration_hours = duration_minutes / 60.0
            end_t = start_t + duration_hours

            CT_info[sid_unique] = {
                'date': pure_date,
                'start': start_t,
                'end': end_t,
                'campus': campus,
                'original_id': sid_original
            }

        except ValueError as e:
            print(f"❌ ERROR processing shift metadata: {str(e)}")
            raise
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR at row {idx}: {type(e).__name__}: {str(e)}")
            raise

    print(f"✓ Successfully loaded:")
    print(f"  - {len(CB)} staff members")
    print(f"  - {len(CT)} unique shifts")
    print(f"  - {len(K)} campuses")
    print(f"  - {len(R)} roles")

    cap_series = df.groupby(['Unique_Shift_ID', 'Vai_tro'])['MS của CÁN BỘ COI THI'].count()
    Cap_jr = cap_series.to_dict()

    # Validate dictionary format
    if not all(isinstance(k, tuple) and len(k) == 2 for k in Cap_jr.keys()):
        print(f"⚠️  WARNING: Unexpected Cap_jr format: {list(Cap_jr.keys())[:3]}")

    if not Cap_jr:
        raise ValueError("No capacity requirements found")

    B_ij = {(i, j): 0 for i in CB for j in CT}
    num_busy_slots = int(0.05 * len(CB) * len(CT))
    busy_pairs = random.sample(list(B_ij.keys()), num_busy_slots)
    for pair in busy_pairs:
        B_ij[pair] = 1

    np.random.seed(42)
    random.seed(42)

    role_level_map = {'CBCT': 1, 'Thuky': 2, 'TruongHD': 3}
    L_i = {}
    unknown_roles_encountered = set()

    for i in CB:
        roles_done = df[df['MS của CÁN BỘ COI THI'] == i]['Vai_tro'].unique()

        levels = []
        for r in roles_done:
            if r in role_level_map:
                levels.append(role_level_map[r])
            else:
                # Unknown role - record it
                unknown_roles_encountered.add(r)
                levels.append(1)  # Default to basic level

        L_i[i] = max(levels) if levels else 3

    # Report unknown roles if any found
    if unknown_roles_encountered:
        print("\n⚠️  WARNING: Unknown roles found in data:")
        for unknown_role in sorted(unknown_roles_encountered):
            staff_with_role = df[df['Vai_tro'] == unknown_role]['MS của CÁN BỘ COI THI'].unique()
            print(f"  - '{unknown_role}': {len(staff_with_role)} staff members")
            print(f"    These staff have been assigned level 1 (basic)")
        print("  If these roles should be recognized, update role_level_map\n")

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
    """
    Interactive menu to adjust data before running solver.

    Options:
    1. View staff information
    2. Update staff qualification level
    3. Update campus preferences
    4. Update busy status
    0. Exit and run solver
    """
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

        # Validate choice
        if choice not in ['0', '1', '2', '3', '4']:
            print(f"❌ Lựa chọn không hợp lệ: '{choice}'")
            print(f"   Vui lòng nhập một trong các số: 0, 1, 2, 3, 4")
            input("   Nhấn Enter để tiếp tục...")
            continue

        if choice == '0':
            print(">>> Dữ liệu đã sẵn sàng.")
            break
        elif choice == '1':
            _view_staff_info(CB, CT, K, L_i, Campus_like_ik, B_ij)
        elif choice == '2':
            _update_staff_qualification(CB, L_i)
        elif choice == '3':
            _update_campus_preference(CB, K, Campus_like_ik)
        elif choice == '4':
            _update_busy_status(CB, CT, B_ij)


def _view_staff_info(CB, CT, K, L_i, Campus_like_ik, B_ij):
    """View detailed information for a staff member."""
    staff_id = input("Nhập mã cán bộ (VD: CB001): ").strip()
    if staff_id not in CB:
        print(f"❌ Mã cán bộ '{staff_id}' không tồn tại.")
        if CB:
            print(f"   Mã có sẵn: {', '.join(CB[:5])}{'...' if len(CB) > 5 else ''}")
        return

    print(f"\n[Dữ liệu hiện tại của {staff_id}]:")
    print(f"- Năng lực (L_i): {L_i[staff_id]}")
    for k in K:
        print(f"- Mức độ thích {k}: {Campus_like_ik.get((staff_id, k))}")
    busy_shifts = [j for j in CT if B_ij.get((staff_id, j)) == 1]
    print(f"- Số ca thi đang bị bận (B_ij=1): {len(busy_shifts)}")


def _update_staff_qualification(CB, L_i):
    """Update staff qualification level with validation and retry."""
    staff_id = input("Nhập mã cán bộ: ").strip()
    if staff_id not in CB:
        print(f"❌ Mã cán bộ '{staff_id}' không tồn tại.")
        return

    while True:
        try:
            new_val = input("Nhập năng lực mới (1, 2 hoặc 3): ").strip()
            new_val = int(new_val)

            if new_val not in [1, 2, 3]:
                print(f"❌ Giá trị '{new_val}' không hợp lệ.")
                print(f"   Vui lòng nhập: 1 (CBCT), 2 (Thư ký), 3 (Trưởng HĐ)")
                continue

            L_i[staff_id] = new_val
            print(f"✓ Cập nhật thành công: {staff_id} → Năng lực {new_val}")
            break

        except ValueError:
            print(f"❌ Lỗi: Nhập không hợp lệ.")
            print(f"   Vui lòng nhập một số: 1, 2 hoặc 3")
        except KeyboardInterrupt:
            print("\n❌ Đã hủy bỏ")
            break


def _update_campus_preference(CB, K, Campus_like_ik):
    """Update campus preference with validation and retry."""
    staff_id = input("Nhập mã cán bộ: ").strip()
    if staff_id not in CB:
        print(f"❌ Mã cán bộ '{staff_id}' không tồn tại.")
        return

    for k in K:
        while True:
            try:
                new_val = input(f" - Mức thích {k} (1: Ghét, 2: BT, 3: Thích): ").strip()
                new_val = int(new_val)

                if new_val not in [1, 2, 3]:
                    print(f"   ❌ Giá trị '{new_val}' không hợp lệ. Vui lòng nhập 1, 2 hoặc 3")
                    continue

                Campus_like_ik[(staff_id, k)] = new_val
                break

            except ValueError:
                print(f"   ❌ Lỗi: Nhập không hợp lệ. Vui lòng nhập số: 1, 2 hoặc 3")
            except KeyboardInterrupt:
                print("\n   ❌ Đã hủy bỏ")
                return

    print(f"✓ Cập nhật thành công: {staff_id}")


def _update_busy_status(CB, CT, B_ij):
    """Update busy status with validation and retry."""
    staff_id = input("Nhập mã cán bộ: ").strip()
    if staff_id not in CB:
        print(f"❌ Mã cán bộ '{staff_id}' không tồn tại.")
        return

    shift_id_input = input("Nhập mã ca thi (Hoặc ID|Campus): ").strip()

    # Handle both original ID and Unique ID for convenience
    matching_shifts = [j for j in CT if j == shift_id_input or j.startswith(shift_id_input + "|")]

    if not matching_shifts:
        print(f"❌ Mã ca thi '{shift_id_input}' không tồn tại.")
        return

    # If multiple matches (same ID at different campuses), ask for clarification
    if len(matching_shifts) > 1:
        print(f"⚠️  Tìm thấy nhiều ca thi trùng ID:")
        for idx, s in enumerate(matching_shifts):
            print(f"   {idx+1}. {s}")
        try:
            choice = int(input(f"Chọn (1-{len(matching_shifts)}): "))
            shift_id = matching_shifts[choice-1]
        except (ValueError, IndexError):
            print("❌ Lựa chọn không hợp lệ.")
            return
    else:
        shift_id = matching_shifts[0]

    while True:
        try:
            new_val = input(f"Trạng thái bận của {shift_id} (1: Bận, 0: Rảnh): ").strip()
            new_val = int(new_val)

            if new_val not in [0, 1]:
                print(f"❌ Giá trị '{new_val}' không hợp lệ. Vui lòng nhập 0 hoặc 1")
                continue

            B_ij[(staff_id, shift_id)] = new_val
            status = "Bận" if new_val == 1 else "Rảnh"
            print(f"✓ Cập nhật thành công: {staff_id} - {shift_id} → {status}")
            break

        except ValueError:
            print(f"❌ Lỗi: Nhập không hợp lệ. Vui lòng nhập số: 0 hoặc 1")
        except KeyboardInterrupt:
            print("\n❌ Đã hủy bỏ")
            break