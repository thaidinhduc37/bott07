import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import {
  adminApi,
  type CreateUserPayload,
} from '@/services/admin-api';
import { catalogApi, type ClassItem } from '@/services/catalog-api';
import { facultyApi, type FacultyItem } from '@/services/faculty-api';
import { ROLE_LABEL, type RoleCode } from '@/utils/roles';

/**
 * Hộp thoại tạo tài khoản mới (chỉ ADMIN) trong trang Tài khoản.
 *
 * Dùng `<dialog>` gốc với `showModal()`: Esc đóng, focus tự bị giữ trong dialog
 * và trả về nút đã mở khi đóng (giống `TrainingDialog` / `ScheduleFormDialog`).
 * Nút mở được truyền qua `openRef` để focus trả về đúng chỗ.
 *
 * Vai trò STUDENT và các vai trò cán bộ (LECTURER, DEPARTMENT_HEAD) không được
 * chọn đồng thời: chọn một bên thì bên kia bị tắt kèm chú thích.
 */

/** Thứ tự hiển thị nhóm vai trò trong form. */
const ROLE_ORDER: RoleCode[] = [
  'STUDENT',
  'LECTURER',
  'ACADEMIC_MANAGER',
  'APPROVER',
  'DEPARTMENT_HEAD',
  'ADMIN',
];

/**
 * Sinh mật khẩu ngẫu nhiên 12 ký tự gồm chữ hoa, chữ thường và số bằng
 * `crypto.getRandomValues` — không dùng `Math.random` để tránh dự đoán được.
 */
function generatePassword(): string {
  const upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const lower = 'abcdefghijkmnpqrstuvwxyz';
  const digits = '23456789';
  const all = upper + lower + digits;
  const buf = new Uint32Array(12);
  crypto.getRandomValues(buf);
  let out = '';
  for (let i = 0; i < 12; i++) {
    out += all[buf[i] % all.length];
  }
  return out;
}

export function CreateUserDialog({
  openRef,
  onClose,
  onCreated,
}: {
  /** Ref trỏ về nút "Tạo tài khoản" để trả focus khi dialog đóng. */
  openRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  onCreated: (email: string) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Trường chung.
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [roles, setRoles] = useState<RoleCode[]>([]);

  // Trường riêng cho STUDENT.
  const [studentCode, setStudentCode] = useState('');
  const [classCode, setClassCode] = useState('');
  const [cohort, setCohort] = useState('');
  const [trainingSystem, setTrainingSystem] = useState('');

  // Trường riêng cho cán bộ (LECTURER / DEPARTMENT_HEAD, không kèm STUDENT).
  const [facultyId, setFacultyId] = useState('');

  // Danh sách lớp / khoa để đổ vào select.
  const [classes, setClasses] = useState<ClassItem[]>([]);
  const [faculties, setFaculties] = useState<FacultyItem[]>([]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    dialogRef.current?.showModal();
    // Trả focus về nút mở khi đóng (bấm backdrop, Esc, hay nút đóng).
    const d = dialogRef.current;
    const onClosed = () => openRef.current?.focus();
    d?.addEventListener('close', onClosed);
    return () => d?.removeEventListener('close', onClosed);
  }, [openRef]);

  useEffect(() => {
    catalogApi
      .classes()
      .then((r) => setClasses(r.items))
      .catch(() => setClasses([]));
    facultyApi
      .list()
      .then((r) => setFaculties(r.items))
      .catch(() => setFaculties([]));
  }, []);

  const isStudent = roles.includes('STUDENT');
  const isStaff = roles.some((r) => r !== 'STUDENT');
  // Cán bộ (không học viên) cần chọn khoa.
  const needsFaculty = (roles.includes('LECTURER') || roles.includes('DEPARTMENT_HEAD')) && !isStudent;

  function toggleRole(r: RoleCode) {
    setRoles((prev) => {
      if (prev.includes(r)) return prev.filter((x) => x !== r);
      // Bật STUDENT thì loại mọi vai trò cán bộ; bật cán bộ thì loại STUDENT.
      if (r === 'STUDENT') return ['STUDENT'];
      return [...prev.filter((x) => x !== 'STUDENT'), r];
    });
  }

  function close() {
    dialogRef.current?.close();
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);

    const payload: CreateUserPayload = {
      email: email.trim(),
      fullName: fullName.trim(),
      password,
      roles,
    };
    const phoneTrim = phone.trim();
    if (phoneTrim) payload.phone = phoneTrim;

    if (isStudent) {
      payload.studentCode = studentCode.trim();
      if (classCode) payload.classCode = classCode;
      if (cohort.trim()) payload.cohort = cohort.trim();
      if (trainingSystem.trim()) payload.trainingSystem = trainingSystem.trim();
    } else if (needsFaculty && facultyId) {
      payload.facultyId = facultyId;
    }

    try {
      await adminApi.createUser(payload);
      onCreated(payload.email);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không tạo được tài khoản.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="acct-new-dlg"
      aria-labelledby="acct-new-title"
      onClose={onClose}
    >
      <div className="acct-new-dlg__bar">
        <h2 id="acct-new-title" className="acct-new-dlg__title">
          Tạo tài khoản
        </h2>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={close}
          aria-label="Đóng hộp thoại"
        >
          <Icon name="close" size={16} />
          <span className="sr-only">Đóng</span>
        </button>
      </div>

      <div className="acct-new-dlg__body">
        <form onSubmit={(e) => void submit(e)} noValidate>
          <div className="field">
            <label className="field__label" htmlFor="acct-new-name">
              Họ và tên<span className="req">*</span>
            </label>
            <input
              id="acct-new-name"
              className="field__input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              minLength={2}
              placeholder="VD: Nguyễn Văn A"
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="acct-new-email">
              Email<span className="req">*</span>
            </label>
            <input
              id="acct-new-email"
              className="field__input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="VD: nguyenvana@hvc.edu.vn"
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="acct-new-phone">
              Số điện thoại
            </label>
            <input
              id="acct-new-phone"
              className="field__input"
              inputMode="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="VD: 0912345678"
            />
            <span className="field__hint">Tùy chọn — 10 đến 11 số, bắt đầu bằng 0.</span>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="acct-new-pass">
              Mật khẩu tạm<span className="req">*</span>
            </label>
            <div className="acct-new-pass">
              <input
                id="acct-new-pass"
                className="field__input"
                type="text"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setPassword(generatePassword())}
              >
                <Icon name="pencil" size={14} />
                Tạo ngẫu nhiên
              </button>
            </div>
            <span className="field__hint">
              Gửi mật khẩu này cho người dùng và yêu cầu đổi sau khi đăng nhập.
            </span>
          </div>

          <fieldset className="acct-new-roles">
            <legend className="acct-new-roles__legend">
              Vai trò<span className="req">*</span>
            </legend>
            <div className="acct-new-roles__grid">
              {ROLE_ORDER.map((r) => {
                const disabled =
                  (r === 'STUDENT' && isStaff) || (r !== 'STUDENT' && isStudent);
                return (
                  <label
                    key={r}
                    className="acct-new-roles__item"
                    title={disabled ? 'Không thể chọn đồng thời với vai trò đã chọn.' : undefined}
                  >
                    <input
                      type="checkbox"
                      checked={roles.includes(r)}
                      disabled={disabled}
                      onChange={() => toggleRole(r)}
                    />
                    {ROLE_LABEL[r]}
                  </label>
                );
              })}
            </div>
            {roles.length === 0 && (
              <span className="field__error">Chọn ít nhất một vai trò.</span>
            )}
            {isStudent && (
              <span className="field__hint">
                Chọn Học viên thì không thể chọn vai trò cán bộ.
              </span>
            )}
            {isStaff && (
              <span className="field__hint">
                Chọn vai trò cán bộ thì không thể chọn Học viên.
              </span>
            )}
          </fieldset>

          {isStudent && (
            <>
              <div className="field">
                <label className="field__label" htmlFor="acct-new-student-code">
                  Mã học viên<span className="req">*</span>
                </label>
                <input
                  id="acct-new-student-code"
                  className="field__input"
                  value={studentCode}
                  onChange={(e) => setStudentCode(e.target.value)}
                  required
                  placeholder="VD: HV2025001"
                />
              </div>

              <div className="field">
                <label className="field__label" htmlFor="acct-new-class">
                  Lớp
                </label>
                <select
                  id="acct-new-class"
                  className="field__input"
                  value={classCode}
                  onChange={(e) => setClassCode(e.target.value)}
                >
                  <option value="">— Chưa xếp lớp —</option>
                  {classes.map((c) => (
                    <option key={c.id} value={c.code}>
                      {c.code} — {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field-grid">
                <div className="field">
                  <label className="field__label" htmlFor="acct-new-cohort">
                    Khóa
                  </label>
                  <input
                    id="acct-new-cohort"
                    className="field__input"
                    value={cohort}
                    onChange={(e) => setCohort(e.target.value)}
                    placeholder="VD: B3"
                  />
                </div>
                <div className="field">
                  <label className="field__label" htmlFor="acct-new-system">
                    Hệ đào tạo
                  </label>
                  <input
                    id="acct-new-system"
                    className="field__input"
                    value={trainingSystem}
                    onChange={(e) => setTrainingSystem(e.target.value)}
                    placeholder="VD: Chính quy"
                  />
                </div>
              </div>
            </>
          )}

          {needsFaculty && (
            <div className="field">
              <label className="field__label" htmlFor="acct-new-faculty">
                Khoa
              </label>
              <select
                id="acct-new-faculty"
                className="field__input"
                value={facultyId}
                onChange={(e) => setFacultyId(e.target.value)}
              >
                <option value="">— Chưa xếp khoa —</option>
                {faculties.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {error && (
            <p className="notice notice--error" role="alert">
              {error}
            </p>
          )}

          <div className="acct-new-dlg__actions">
            <button type="submit" className="btn btn--primary" disabled={saving || roles.length === 0}>
              {saving ? 'Đang tạo…' : 'Tạo tài khoản'}
            </button>
            <button type="button" className="btn btn--ghost" disabled={saving} onClick={close}>
              Hủy
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
