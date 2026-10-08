import { useState } from 'react';
import { Field } from '@/components/shared/Field';
import type { FieldValue, FormField, TableRowValue } from '@/services/forms-api';

/** `2005-03-14` → `14/03/2005`. Chuỗi rỗng hoặc sai dạng thì trả nguyên. */
function viDate(iso?: string): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

/** Nhãn nguồn của trường autofill, hiển thị cạnh ô bị khóa. */
const SOURCE_LABEL: Record<string, string> = {
  'user.fullName': 'hồ sơ',
  'user.phone': 'hồ sơ',
  'profile.studentCode': 'hồ sơ học vụ',
  'profile.dateOfBirth': 'hồ sơ học vụ',
  'profile.cohort': 'hồ sơ học vụ',
  'profile.trainingSystem': 'hồ sơ học vụ',
  'profile.class.code': 'hồ sơ học vụ',
  'profile.class.name': 'hồ sơ học vụ',
};

export interface SubmissionFormProps {
  fields: FormField[];
  /**
   * Mã biểu mẫu. Cần để đưa ra dòng gợi ý đúng biểu mẫu — gợi ý bám vào tên
   * trường thì hai đơn nghỉ học dùng chung `leaveTo` sẽ hiện chung một câu, và
   * câu đó chỉ đúng với một trong hai.
   */
  templateCode: string;
  autofill: Record<string, string>;
  initial?: Record<string, FieldValue>;
  busy?: boolean;
  submitLabel: string;
  fieldErrors?: string[];
  onSubmit: (formData: Record<string, FieldValue>) => void;
  onCancel?: () => void;
}

/** Dòng gợi ý dưới ô nhập, tra theo (mã đơn, tên trường): `leaveTo` có ở cả hai đơn nghỉ học nhưng phạm vi ngày ngược nhau. */
const HINTS: Record<string, Record<string, string>> = {
  DON_XIN_NGHI_HOC: {
    leaveTo: 'Biểu mẫu này dùng cho nghỉ từ 01 đến 03 ngày.',
    courseCode: 'Để trống nếu việc nghỉ không rơi vào buổi học của môn nào.',
  },
  DON_XIN_NGHI_HOC_TREN_3: {
    leaveTo: 'Biểu mẫu này dùng cho nghỉ TRÊN 03 ngày. Nghỉ ngắn hơn thì dùng biểu mẫu 01–03 ngày.',
  },
  DON_XIN_HOC_BO_SUNG: {
    soTietNghi: 'Đơn này áp dụng khi số tiết nghỉ vượt quá 20% số tiết quy định.',
  },
};

/**
 * Bảng lặp dòng cho trường `type: 'table'`. Số thứ tự do đây tự đánh (giống renderer DOCX) để đơn không nhảy số; nút xóa bị vô hiệu
 * khi chỉ còn một dòng.
 */
function RepeatingTable({
  field,
  rows,
  onCell,
  onAdd,
  onRemove,
}: {
  field: FormField;
  rows: TableRowValue[];
  onCell: (i: number, col: string, v: string) => void;
  onAdd: () => void;
  onRemove: (i: number) => void;
}) {
  const cols = field.columns ?? [];
  const max = field.maxRows ?? 20;

  return (
    <div style={{ margin: '0 0 var(--gap-5)' }}>
      <div className="label" style={{ marginBottom: 'var(--gap-2)' }}>
        {field.label}
        {field.required && <span aria-hidden="true"> *</span>}
      </div>

      {/* Bảng co giãn theo bề rộng KHUNG CHỨA (container query `.form-table`): đủ
          rộng thì là bảng; hẹp (cột nhập liệu 24rem của trang lập đơn, điện thoại)
          thì mỗi dòng thành một khối, mỗi ô kèm nhãn cột. Trước đây bảng 4 cột nằm
          trong khung ~15rem, hai cột cuối bị đẩy ra ngoài và ô nhập không thấy. */}
      <div className="form-table">
        <table className="data-table form-table__table">
          <thead>
            <tr>
              <th scope="col" style={{ width: '3rem' }}>
                STT
              </th>
              {cols.map((c) => (
                <th key={c.key} scope="col">
                  {c.label}
                </th>
              ))}
              <th scope="col" style={{ width: '3rem' }}>
                <span className="sr-only">Xóa dòng</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="form-table__no" data-label="Dòng">
                  {i + 1}
                </td>
                {cols.map((c) => (
                  <td key={c.key} data-label={c.label}>
                    <input
                      className="field__input"
                      type="text"
                      maxLength={c.maxLength}
                      value={r[c.key] ?? ''}
                      aria-label={`${c.label}, dòng ${i + 1}`}
                      onChange={(e) => onCell(i, c.key, e.target.value)}
                    />
                  </td>
                ))}
                <td className="form-table__del">
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={rows.length <= 1}
                    aria-label={`Xóa dòng ${i + 1}`}
                    onClick={() => onRemove(i)}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        type="button"
        className="btn btn--ghost"
        style={{ marginTop: 'var(--gap-2)' }}
        disabled={rows.length >= max}
        onClick={onAdd}
      >
        + Thêm dòng
      </button>
      {rows.length >= max && (
        <p className="prose" style={{ fontSize: '0.8125rem', margin: 'var(--gap-2) 0 0' }}>
          Tối đa {max} dòng.
        </p>
      )}
    </div>
  );
}

/** Một dòng rỗng đúng theo các cột đã khai. */
function emptyRow(f: FormField): TableRowValue {
  return Object.fromEntries((f.columns ?? []).map((c) => [c.key, '']));
}

/**
 * Biểu mẫu lập đơn. Trường `autofill` hiện dạng ô khóa có nhãn nói rõ lấy từ đâu và KHÔNG nằm trong dữ liệu gửi đi: máy chủ tự lấy
 * từ hồ sơ của phiên và bỏ mọi khóa autofill client gửi lên. Khóa ô chỉ để người dùng hiểu; bảo vệ nằm ở `FormsService`.
 */
export function SubmissionForm({
  fields,
  templateCode,
  autofill,
  initial = {},
  busy,
  submitLabel,
  fieldErrors,
  onSubmit,
  onCancel,
}: SubmissionFormProps) {
  const editable = fields.filter((f) => !f.autofill);
  const locked = fields.filter((f) => f.autofill);

  const [values, setValues] = useState<Record<string, FieldValue>>(() =>
    Object.fromEntries(
      editable.map((f) => {
        if (f.type !== 'table') return [f.key, (initial[f.key] as string) ?? ''];
        const saved = initial[f.key];
        const rows = Array.isArray(saved) ? saved : [];
        // Mở sẵn hai dòng trống: bảng không có dòng nào thì người dùng không có
        // gì để bấm vào, và nút "Thêm dòng" một mình trông như lỗi hiển thị.
        return [f.key, rows.length ? rows : [emptyRow(f), emptyRow(f)]];
      }),
    ),
  );

  function set(key: string, v: FieldValue) {
    setValues((prev) => ({ ...prev, [key]: v }));
  }

  function text(key: string): string {
    const v = values[key];
    return typeof v === 'string' ? v : '';
  }

  function rowsOf(key: string): TableRowValue[] {
    const v = values[key];
    return Array.isArray(v) ? v : [];
  }

  function setCell(f: FormField, i: number, col: string, v: string) {
    const rows = rowsOf(f.key).map((r, j) => (j === i ? { ...r, [col]: v } : r));
    set(f.key, rows);
  }

  return (
    // `paper-form` là chỗ duy nhất trong ứng dụng còn dùng dòng chấm điền tay.
    //
    // Đây là quy tắc của hệ thiết kế, không phải một lựa chọn ở riêng tệp này:
    // ẩn dụ giấy tờ chỉ được dùng khi vật thật đúng là một tờ giấy. Ở đây nó
    // đúng theo nghĩa đen — người dùng đang điền một tờ đơn sẽ được ký, kết xuất
    // ra PDF và in. Ô nhập ở màn đăng nhập hay ô hỏi đáp thì không, nên chúng
    // dùng ô nền mềm bo góc như mọi phần mềm khác.
    <form
      className="sheet sheet--pad paper-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(values);
      }}
    >
      <section>
        <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-3)' }}>
          Thông tin lấy sẵn từ hồ sơ
        </h2>
        <p className="prose" style={{ fontSize: '0.8125rem', margin: '0 0 var(--gap-5)' }}>
          Bạn không sửa được những ô này. Đơn đã ký phải khớp với dữ liệu học vụ; nếu có sai sót,
          báo Phòng Quản lý học viên rồi lập lại đơn.
        </p>
        <div className="field-grid">
          {locked.map((f) => (
            <Field
              key={f.key}
              label={f.label}
              // Ô khóa là để đọc, nên hiển thị theo cách người Việt viết ngày.
              // Giá trị gửi đi vẫn là ISO vì máy chủ tự lấy từ hồ sơ, không lấy
              // từ ô này.
              value={f.type === 'date' ? viDate(autofill[f.key]) : (autofill[f.key] ?? '')}
              readOnly
              autofilledFrom={SOURCE_LABEL[f.autofill!] ?? 'hồ sơ'}
              onChange={() => undefined}
            />
          ))}
        </div>
      </section>

      <section style={{ marginTop: 'var(--gap-8)' }}>
        <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-4)' }}>
          Phần bạn điền
        </h2>
        {editable.map((f) =>
          f.type === 'table' ? (
            <RepeatingTable
              key={f.key}
              field={f}
              rows={rowsOf(f.key)}
              onCell={(i, col, v) => setCell(f, i, col, v)}
              onAdd={() => set(f.key, [...rowsOf(f.key), emptyRow(f)])}
              onRemove={(i) => set(f.key, rowsOf(f.key).filter((_, j) => j !== i))}
            />
          ) : f.type === 'textarea' ? (
            <Field
              key={f.key}
              as="textarea"
              rows={4}
              label={f.label}
              required={f.required}
              maxLength={f.maxLength}
              value={text(f.key)}
              onChange={(e) => set(f.key, e.target.value)}
              hint={
                f.maxLength ? `Còn ${f.maxLength - text(f.key).length} ký tự` : undefined
              }
            />
          ) : (
            <Field
              key={f.key}
              type={f.type === 'date' ? 'date' : 'text'}
              label={f.label}
              required={f.required}
              maxLength={f.maxLength}
              value={text(f.key)}
              onChange={(e) => set(f.key, e.target.value)}
              hint={HINTS[templateCode]?.[f.key]}
            />
          ),
        )}
      </section>

      {fieldErrors && fieldErrors.length > 0 && (
        <div className="notice notice--error" role="alert" style={{ marginTop: 'var(--gap-5)' }}>
          <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
            {fieldErrors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="row" style={{ marginTop: 'var(--gap-6)' }}>
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? 'Đang lưu…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={busy}>
            Hủy
          </button>
        )}
      </div>
    </form>
  );
}
