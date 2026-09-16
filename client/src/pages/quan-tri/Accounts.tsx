import { useCallback, useEffect, useState } from 'react';
import { useSession } from '@/components/shared/SessionProvider';
import {
  USER_STATUS_LABEL,
  USER_STATUS_TAG,
  adminApi,
  type AdminUser,
  type UserStatus,
} from '@/services/admin-api';
import { ROLE_LABEL, type RoleCode } from '@/utils/roles';
import { viDateTime } from '@/services/forms-api';

const ALL_ROLES: RoleCode[] = ['ADMIN', 'ACADEMIC_MANAGER', 'LECTURER', 'APPROVER', 'STUDENT'];

export default function AccountsPage() {
  const { user: me } = useSession();
  const [items, setItems] = useState<AdminUser[]>([]);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems((await adminApi.users({ search: search || undefined, role: roleFilter || undefined })).items);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [search, roleFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(fn: () => Promise<unknown>, message: string) {
    setError(null);
    setFlash(null);
    try {
      await fn();
      setFlash(message);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="stack">
      <header>
        <span className="eyebrow">Người dùng</span>
        <h1 className="display page-title">
          Tài khoản và vai trò
        </h1>
        <p className="page-sub">
          Khóa một tài khoản sẽ cắt mọi phiên đang mở của người đó. Gỡ vai trò có hiệu lực chậm nhất
          sau 15 phút — thời gian sống của access token; nếu cần chặn ngay thì khóa tài khoản.
        </p>
      </header>

      {flash && (
        <div className="notice notice--ok" role="status">
          {flash}
        </div>
      )}
      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      <div className="sheet" style={{ padding: '0.85rem 1.1rem' }}>
        <div className="row" style={{ gap: 'var(--gap-4)', flexWrap: 'wrap' }}>
          <label style={{ flex: '1 1 14rem' }}>
            <span className="field__label">Tìm theo tên, email hoặc mã học viên</span>
            <input className="field__input" value={search} onChange={(e) => setSearch(e.target.value)} />
          </label>
          <label style={{ flex: '0 1 16rem' }}>
            <span className="field__label">Vai trò</span>
            <select className="field__input" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
              <option value="">Tất cả vai trò</option>
              {ALL_ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: '1px', background: 'var(--rule-faint)', border: '1px solid var(--rule-faint)' }}>
          {items.map((u) => {
            const isMe = u.id === me?.id;
            return (
              <li key={u.id} style={{ background: 'var(--sheet)', padding: '1rem 1.15rem' }}>
                <div className="spread" style={{ alignItems: 'flex-start', gap: 'var(--gap-4)' }}>
                  <div style={{ minWidth: 0 }}>
                    <h2 className="display" style={{ fontSize: '1rem', margin: 0 }}>
                      {u.fullName}
                      {isMe && (
                        <span className="tag tag--muted" style={{ marginLeft: '0.5rem' }}>
                          bạn
                        </span>
                      )}
                    </h2>
                    <p className="mono" style={{ margin: '0.2rem 0 0', fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>
                      {u.email}
                      {u.studentProfile && ` · ${u.studentProfile.studentCode}`}
                      {u.studentProfile?.studyClass && ` · ${u.studentProfile.studyClass.code}`}
                    </p>
                    <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
                      {u.roles.map((r) => ROLE_LABEL[r]).join(' · ')}
                      {' — '}
                      {u.lastLoginAt ? `đăng nhập gần nhất ${viDateTime(u.lastLoginAt)}` : 'chưa đăng nhập lần nào'}
                    </p>
                  </div>
                  <span className={`tag ${USER_STATUS_TAG[u.status]}`} style={{ flexShrink: 0 }}>
                    {USER_STATUS_LABEL[u.status]}
                  </span>
                </div>

                {editing === u.id ? (
                  <RoleEditor
                    user={u}
                    onCancel={() => setEditing(null)}
                    onSave={(roles) =>
                      act(async () => {
                        await adminApi.setRoles(u.id, roles);
                        setEditing(null);
                      }, `Đã cập nhật vai trò cho ${u.fullName}.`)
                    }
                  />
                ) : (
                  <div className="row" style={{ marginTop: 'var(--gap-4)', gap: 'var(--gap-3)', flexWrap: 'wrap' }}>
                    <button type="button" className="btn btn--ghost" onClick={() => setEditing(u.id)} disabled={isMe}>
                      Đổi vai trò
                    </button>
                    {(['ACTIVE', 'SUSPENDED', 'DISABLED'] as UserStatus[])
                      .filter((s) => s !== u.status)
                      .map((s) => (
                        <button
                          key={s}
                          type="button"
                          className={`btn ${s === 'ACTIVE' ? 'btn--ghost' : 'btn--danger'}`}
                          disabled={isMe}
                          onClick={() =>
                            act(
                              () => adminApi.setStatus(u.id, s),
                              `${u.fullName}: ${USER_STATUS_LABEL[s].toLowerCase()}.`,
                            )
                          }
                        >
                          {s === 'ACTIVE' ? 'Mở khóa' : s === 'SUSPENDED' ? 'Tạm khóa' : 'Vô hiệu hóa'}
                        </button>
                      ))}
                    {isMe && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', alignSelf: 'center' }}>
                        Không tự đổi vai trò hay khóa chính mình — đó là cách nhanh nhất để mất quyền
                        quản trị mà không ai mở lại được.
                      </span>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function RoleEditor({
  user,
  onSave,
  onCancel,
}: {
  user: AdminUser;
  onSave: (roles: RoleCode[]) => void;
  onCancel: () => void;
}) {
  const [roles, setRoles] = useState<RoleCode[]>(user.roles);

  function toggle(r: RoleCode) {
    setRoles((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]));
  }

  return (
    <div style={{ marginTop: 'var(--gap-4)', borderTop: '1px dotted var(--rule)', paddingTop: 'var(--gap-4)' }}>
      <div className="row" style={{ gap: 'var(--gap-4)', flexWrap: 'wrap' }}>
        {ALL_ROLES.map((r) => (
          <label key={r} className="row" style={{ gap: '0.4rem', fontSize: '0.875rem' }}>
            <input type="checkbox" checked={roles.includes(r)} onChange={() => toggle(r)} />
            {ROLE_LABEL[r]}
          </label>
        ))}
      </div>
      <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
        <button type="button" className="btn btn--primary" disabled={roles.length === 0} onClick={() => onSave(roles)}>
          Lưu vai trò
        </button>
        <button type="button" className="btn btn--ghost" onClick={onCancel}>
          Hủy
        </button>
      </div>
      {roles.length === 0 && (
        <p style={{ fontSize: '0.75rem', color: 'var(--seal)', margin: 'var(--gap-2) 0 0' }}>
          Tài khoản phải có ít nhất một vai trò.
        </p>
      )}
    </div>
  );
}
