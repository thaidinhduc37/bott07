#!/usr/bin/env python3
"""
Script chuẩn hóa các file corpus bị xuống hàng sớm (hard line breaks).
Gộp các dòng kết thúc bằng dấu phẩy, chấm phẩy với dòng tiếp theo.
"""

import re
from pathlib import Path

def should_join_next_line(current_line, next_line):
    """
    Kiểm tra xem có nên gộp dòng hiện tại với dòng kế tiếp không.

    Args:
        current_line: Dòng hiện tại
        next_line: Dòng kế tiếp

    Returns:
        True nếu nên gộp, False nếu không
    """
    if not current_line or not next_line:
        return False

    current = current_line.rstrip()
    next_stripped = next_line.strip()

    # Không gộp nếu dòng tiếp theo là blank
    if not next_stripped:
        return False

    # Không gộp nếu dòng tiếp theo là markdown heading
    if re.match(r'^#{1,6}\s', next_line):
        return False

    # Không gộp nếu dòng tiếp theo là list item
    if re.match(r'^\s*[-*+]\s', next_line):
        return False

    if re.match(r'^\s*\d+\.\s', next_line):
        return False

    # Không gộp nếu dòng tiếp theo là table
    if re.match(r'^\s*\|', next_line):
        return False

    # Không gộp nếu dòng hiện tại là heading
    if re.match(r'^#{1,6}\s', current_line):
        return False

    # GỘP nếu dòng hiện tại kết thúc bằng dấu phẩy, chấm phẩy hoặc "và"
    if re.search(r'[,;]$', current):
        return True

    if re.search(r'\svà$', current):
        return True

    # GỘP nếu dòng tiếp theo bắt đầu bằng indent (3+ spaces) và chữ thường
    if re.match(r'^   [a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]', next_line):
        return True

    return False

def fix_line_breaks(input_file, output_file=None):
    """
    Sửa lỗi xuống hàng sớm trong file.

    Args:
        input_file: Path đến file đầu vào
        output_file: Path đến file đầu ra (nếu None, ghi đè file gốc)
    """
    input_path = Path(input_file)

    if not input_path.exists():
        print(f"Lỗi: File không tồn tại: {input_file}")
        return False

    # Doc file
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Loi khi doc file {input_file}: {e}")
        return False

    print(f"Dang xu ly: {input_path.name}")
    print(f"  - Tong so dong goc: {len(lines)}")

    # Xu ly gop dong
    fixed_lines = []
    i = 0
    join_count = 0

    while i < len(lines):
        current_line = lines[i]

        # Kiem tra xem co nen gop voi dong ke tiep khong
        if i + 1 < len(lines) and should_join_next_line(current_line, lines[i + 1]):
            # Gop dong
            next_line = lines[i + 1]

            # Loai bo khoang trang thua o dau dong tiep theo
            next_stripped = next_line.strip()

            # Gop voi mot khoang trang
            current_stripped = current_line.rstrip()

            # Neu dong hien tai ket thuc bang dau phay/cham phay, giu nguyen
            if current_stripped.endswith(',') or current_stripped.endswith(';'):
                joined = current_stripped + ' ' + next_stripped + '\n'
            else:
                joined = current_stripped + ' ' + next_stripped + '\n'

            fixed_lines.append(joined)
            i += 2  # Bo qua ca 2 dong
            join_count += 1
        else:
            # Giu nguyen dong
            fixed_lines.append(current_line)
            i += 1

    print(f"  - Da gop: {join_count} cap dong")
    print(f"  - Tong so dong sau xu ly: {len(fixed_lines)}")

    # Ghi file
    output_path = Path(output_file) if output_file else input_path

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(fixed_lines)
        print(f"  [OK] Da ghi: {output_path}")
        return True
    except Exception as e:
        print(f"  [FAIL] Loi khi ghi file {output_path}: {e}")
        return False

def main():
    """Xử lý 4 file cần sửa."""

    corpus_dir = Path('D:/projects/bott07/copus/hoctap')

    problem_files = [
        '1.giao_trinh_triet_hoc_mac_lenin.md',
        '2.giao_trinh_kinh_te_chinh_tri_mac_lenin.md',
        '4.giao_trinh_tu_tuong_ho_chi_minh.md',
        '5.giao_trinh_lich_su_dang_cong_san_viet_nam.md'
    ]

    print("=" * 80)
    print("CHUAN HOA CAC FILE CORPUS BI XUONG HANG SOM")
    print("=" * 80)
    print()

    success_count = 0

    for filename in problem_files:
        input_file = corpus_dir / filename

        # Tao backup truoc khi sua
        backup_file = corpus_dir / f"{filename}.backup"

        try:
            import shutil
            shutil.copy2(input_file, backup_file)
            print(f"[Backup] {backup_file.name}")
        except Exception as e:
            print(f"[Loi] Khong the tao backup cho {filename}: {e}")
            continue

        # Sua file
        if fix_line_breaks(input_file):
            success_count += 1

        print()

    print("=" * 80)
    print(f"Hoan thanh: {success_count}/{len(problem_files)} file duoc xu ly thanh cong")
    print("=" * 80)
    print()
    print("Luu y:")
    print("  - File goc da duoc backup voi duoi .backup")
    print("  - Neu co van de, co the restore tu file backup")
    print("  - Chay lai script analyze_line_breaks.py de kiem tra ket qua")

if __name__ == '__main__':
    main()
