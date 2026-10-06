#!/usr/bin/env python3
"""
Phân tích các file trong corpus để tìm file có vấn đề xuống hàng sớm.
"""

import re
from pathlib import Path

def analyze_file(filepath):
    """Phân tích một file và trả về thống kê."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Đếm các dòng kết thúc bằng dấu phẩy
        comma_endings = sum(1 for line in lines if line.rstrip().endswith(','))

        # Đếm các dòng kết thúc bằng dấu chấm phẩy
        semicolon_endings = sum(1 for line in lines if line.rstrip().endswith(';'))

        # Đếm các dòng bắt đầu bằng khoảng trắng (indent)
        indented_lines = sum(1 for line in lines if re.match(r'^   [a-zàáảãạ]', line))

        # Đếm các dòng có double-char OCR error
        double_char_lines = sum(1 for line in lines if re.search(r'([A-Z])\1([a-z])\2', line))

        total_lines = len(lines)

        return {
            'comma_endings': comma_endings,
            'semicolon_endings': semicolon_endings,
            'indented_lines': indented_lines,
            'double_char_lines': double_char_lines,
            'total_lines': total_lines
        }
    except Exception:
        return None

def main():
    corpus_dir = Path(__file__).resolve().parent.parent / 'data' / 'corpus'

    results = []

    # Phân tích các file trong hoctap
    hoctap_dir = corpus_dir / 'giao-trinh'
    for filepath in sorted(hoctap_dir.glob('*.md')):
        stats = analyze_file(filepath)
        if stats:
            results.append((filepath.name, stats))

    # Phân tích các file trong quyche_quydinh
    quyche_dir = corpus_dir / 'quy-che-quy-dinh'
    for filepath in sorted(quyche_dir.glob('*.md')):
        stats = analyze_file(filepath)
        if stats:
            results.append((filepath.name, stats))

    # In kết quả
    print("\n=== BAO CAO PHAN TICH CORPUS ===\n")
    print("=" * 100)
    print(f"{'File':<50} {'Dong ,':<8} {'Dong ;':<8} {'Indent':<8} {'OCR':<6} {'Tong':<8}")
    print("=" * 100)

    problem_files = []

    for filename, stats in results:
        comma = stats['comma_endings']
        semicolon = stats['semicolon_endings']
        indent = stats['indented_lines']
        double = stats['double_char_lines']
        total = stats['total_lines']

        # Đánh dấu file có vấn đề
        is_problem = comma > 20 or double > 5
        marker = "[!]" if is_problem else "[+]"

        print(f"{marker} {filename:<48} {comma:<8} {semicolon:<8} {indent:<8} {double:<6} {total:<8}")

        if is_problem:
            problem_files.append({
                'name': filename,
                'comma': comma,
                'double_char': double
            })

    print("=" * 100)
    print(f"\nTong cong: {len(results)} file")
    print(f"File co van de: {len(problem_files)} file\n")

    if problem_files:
        print("\n=== DANH SACH FILE CAN SUA ===\n")
        for i, pf in enumerate(problem_files, 1):
            reason = []
            if pf['double_char'] > 0:
                reason.append(f"loi OCR double-char ({pf['double_char']} dong)")
            if pf['comma'] > 20:
                reason.append(f"xuong hang som ({pf['comma']} dong ket thuc bang ',')")

            print(f"{i}. {pf['name']}")
            print(f"   - {' + '.join(reason)}")

if __name__ == '__main__':
    main()
