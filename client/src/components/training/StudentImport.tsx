import { CsvImport } from '@/components/shared/CsvImport';
import { Icon } from '@/components/shared/Icon';
import { downloadText } from '@/utils/download';
import { catalogApi, type StudentImportResult } from '@/services/catalog-api';

const COLUMNS = 'ma_hv,ho_ten,email,ma_lop,khoa_hoc,sdt';
const EXAMPLE = 'HV20260001,Nguyễn Văn An,an.nv@hvktcnan.edu.vn,B3D15,2026,0901234567';

const csvCell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);

function downloadCredentials(rows: StudentImportResult['credentials']) {
  const lines = [
    'ma_hv,ho_ten,email,mat_khau',
    ...rows.map((r) => [r.studentCode, r.fullName, r.email, r.password].map(csvCell).join(',')),
  ];
  downloadText('tai-khoan-moi.csv', lines.join('\n') + '\n');
}

/**
 * Nhập danh sách học viên từ CSV (quản lý đào tạo / quản trị): tạo tài khoản mới, cập nhật lớp và họ tên.
 * Mật khẩu của tài khoản mới chỉ có trong kết quả lúc ghi thật nên nút tải nằm ngay tại đó.
 */
export function StudentImport() {
  return (
    <CsvImport<StudentImportResult>
      id="stimp-file"
      run={catalogApi.importStudents}
      columns={COLUMNS}
      exampleRow={EXAMPLE}
      sample={`${COLUMNS}\n${EXAMPLE}\n`}
      sampleName="mau-nhap-hoc-vien.csv"
      submitLabel="Nhập danh sách"
      notes={[
        'Ba cột đầu (ma_hv, ho_ten, email) bắt buộc.',
        'Mã học viên chưa có: tạo tài khoản mới với mật khẩu ngẫu nhiên.',
        'Mã đã có: cập nhật họ tên, lớp, khóa, số điện thoại; ô để trống thì giữ nguyên. Email không đổi qua tệp.',
        'Còn dòng lỗi thì không ghi gì. Chạy lại cùng tệp không tạo trùng.',
        'Một tệp tối đa 1.000 dòng.',
      ]}
      afterResult={(r) =>
        r.accepted && r.credentials.length > 0 ? (
          <div className="notice notice--warn" role="status">
            <p style={{ margin: 0 }}>
              <strong>Mật khẩu của {r.credentials.length} tài khoản mới chỉ hiện lần này.</strong> Hệ thống không lưu
              mật khẩu dạng rõ nên không xem lại được. Tải về và giao cho học viên, nhắc đổi mật khẩu sau khi đăng nhập.
            </p>
            <div style={{ marginTop: 'var(--gap-3)' }}>
              <button
                type="button"
                className="btn btn--primary btn--sm"
                onClick={() => downloadCredentials(r.credentials)}
              >
                <Icon name="form" size={16} />
                Tải danh sách tài khoản mới
              </button>
            </div>
          </div>
        ) : null
      }
    />
  );
}
