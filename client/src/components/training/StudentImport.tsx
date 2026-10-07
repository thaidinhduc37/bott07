import { useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { GradeImportReport } from '@/components/grades/GradeImport';
import { catalogApi, type StudentImportResult } from '@/services/catalog-api';

const COLUMNS = 'ma_hv,ho_ten,email,ma_lop,khoa_hoc,sdt';
const SAMPLE = `${COLUMNS}\nHV20260001,Nguyễn Văn An,an.nv@hvktcnan.edu.vn,B3D15,2026,0901234567\n`;

/** Tải một tệp CSV (có BOM để Excel mở đúng tiếng Việt). */
function download(name: string, text: string) {
  const blob = new Blob(['﻿' + text], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const csvCell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);

function downloadCredentials(rows: StudentImportResult['credentials']) {
  const lines = [
    'ma_hv,ho_ten,email,mat_khau',
    ...rows.map((r) => [r.studentCode, r.fullName, r.email, r.password].map(csvCell).join(',')),
  ];
  download('tai-khoan-moi.csv', lines.join('\n') + '\n');
}

/**
 * Nhập danh sách học viên từ CSV (quản lý đào tạo / quản trị): tạo tài khoản mới, cập nhật lớp và họ tên.
 * "Kiểm tra" chạy `dryRun` (không ghi); chỉ cho nhập khi tệp không còn dòng lỗi.
 * Mật khẩu của tài khoản mới chỉ có trong kết quả lúc ghi thật nên màn hình đưa nút tải ngay tại đó.
 */
export function StudentImport() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<StudentImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await catalogApi.importStudents(file, dryRun));
    } catch (e) {
      setError((e as Error).message || 'Nạp tệp thất bại');
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const canImport = Boolean(file) && result !== null && result.dryRun && result.errors.length === 0;
  const creds = result?.accepted ? result.credentials : [];

  return (
    <div className="page-grid">
      <div className="page-grid__main">
        <form
          className="sheet sheet--pad"
          onSubmit={(e) => {
            e.preventDefault();
            void run(false);
          }}
        >
          <div className="field">
            <label className="field__label" htmlFor="stimp-file">
              Tệp CSV<span className="req">*</span>
            </label>
            <input
              id="stimp-file"
              type="file"
              accept=".csv,text/csv"
              className="field__input"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setResult(null);
                setError(null);
              }}
              style={{ maxWidth: '36rem' }}
            />
            <span className="field__hint">Tệp UTF-8, dòng đầu là tên cột. Bấm “Kiểm tra” trước khi nhập.</span>
          </div>

          <div className="row" style={{ marginTop: 'var(--gap-6)' }}>
            <button type="button" className="btn btn--ghost" onClick={() => void run(true)} disabled={busy || !file}>
              Kiểm tra
            </button>
            <button type="submit" className="btn btn--primary" disabled={busy || !canImport}>
              {busy ? 'Đang xử lý…' : 'Nhập danh sách'}
            </button>
          </div>
        </form>

        {error && (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        )}

        {creds.length > 0 && (
          <div className="notice notice--warn" role="status">
            <p style={{ margin: 0 }}>
              <strong>Mật khẩu của {creds.length} tài khoản mới chỉ hiện lần này.</strong> Hệ thống không lưu mật khẩu
              dạng rõ nên không xem lại được. Tải về và giao cho học viên, nhắc đổi mật khẩu sau khi đăng nhập.
            </p>
            <div style={{ marginTop: 'var(--gap-3)' }}>
              <button type="button" className="btn btn--primary btn--sm" onClick={() => downloadCredentials(creds)}>
                <Icon name="form" size={16} />
                Tải danh sách tài khoản mới
              </button>
            </div>
          </div>
        )}

        {result && <GradeImportReport result={result} />}
      </div>

      <aside className="page-grid__aside">
        <section className="sheet sheet--pad">
          <h2 className="aside-h">Định dạng tệp</h2>
          <p className="field__hint" style={{ margin: '0 0 var(--gap-2)' }}>
            Dòng đầu là tên cột:
          </p>
          <code className="gent-cols">{COLUMNS}</code>
          <p className="field__hint" style={{ marginTop: 'var(--gap-3)' }}>
            Ba cột đầu bắt buộc. Ví dụ một dòng:
          </p>
          <code className="gent-cols">{SAMPLE.trim().split('\n')[1]}</code>
          <div style={{ marginTop: 'var(--gap-5)' }}>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => download('mau-nhap-hoc-vien.csv', SAMPLE)}
            >
              <Icon name="form" size={16} />
              Tải tệp mẫu
            </button>
          </div>
        </section>

        <section className="sheet sheet--pad">
          <h2 className="aside-h">Lưu ý</h2>
          <ul className="gent-notes">
            <li>Mã học viên chưa có: tạo tài khoản mới với mật khẩu ngẫu nhiên.</li>
            <li>
              Mã đã có: cập nhật họ tên, lớp, khóa, số điện thoại; ô để trống thì giữ nguyên. Email không đổi qua tệp.
            </li>
            <li>Còn dòng lỗi thì không ghi gì. Chạy lại cùng tệp không tạo trùng.</li>
            <li>Một tệp tối đa 1.000 dòng.</li>
          </ul>
        </section>
      </aside>
    </div>
  );
}
