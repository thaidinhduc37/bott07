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
import { PageHeader } from '@/components/shared/PageHeader';

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

  // Đếm cho cột phụ "Tổng quan" — tính từ danh sách đã tải, không gọi thêm API.
  const statusCounts = (['ACTIVE', 'SUSPENDED', 'DISABLED'] as UserStatus[]).map((s) => ({
    status: s,
    count: items.filter((u) => u.status === s).length,
  }));
  const roleCounts = ALL_ROLES.map((r) => ({
    role: r,
    count: items.filter((u) => u.roles.includes(r)).length,
  }));

  return (
    <div className="stack">
      <PageHeader eyebrow="Người dùng" title="Tài khoản và vai trò" />

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

      <div className="page-grid">
        <div className="page-grid__main">
          {loading ? (
            <p className="eyebrow">Đang tải…</p>
          ) : (
            <div className="sheet">
              <ul className="acct-list">
              {items.map((u) => {
                const isMe = u.id === me?.id;
                return (
                  <li key={u.id} className="acct-list__item">
                    <div className="acct-row">
                      <div className="acct-row__body">
                        <h2 className="acct-row__name">
                          {u.fullName}
                          {isMe && <span className="tag tag--muted">bạn</span>}
                        </h2>
                        <p className="acct-row__meta">
                          <span className="mono">{u.email}</span>
                          {u.studentProfile && <span className="mono"> · {u.studentProfile.studentCode}</span>}
                          <span> · {u.roles.map((r) => ROLE_LABEL[r]).join(' · ')}</span>
                          <span> · {u.lastLoginAt ? `đăng nhập gần nhất ${viDateTime(u.lastLoginAt)}` : 'chưa đăng nhập'}</span>
                        </p>
                      </div>
                      <div className="acct-row__side">
                        <span className={`tag ${USER_STATUS_TAG[u.status]}`}>
                          {USER_STATUS_LABEL[u.status]}
                        </span>
                        {isMe ? (
                          <span className="acct-row__self">Không tự đổi vai trò hay khóa chính mình</span>
                        ) : (
                          <div className="acct-row__actions">
                            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setEditing(u.id)}>
                              Đổi vai trò
                            </button>
                            {(['ACTIVE', 'SUSPENDED', 'DISABLED'] as UserStatus[])
                              .filter((s) => s !== u.status)
                              .map((s) => (
                                <button
                                  key={s}
                                  type="button"
                                  className={`btn btn--quiet btn--sm ${s === 'ACTIVE' ? '' : 'acct-row__danger'}`}
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
                          </div>
                        )}
                      </div>
                    </div>

                    {editing === u.id && (
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
                    )}
                  </li>
                );
              })}
              </ul>
            </div>
          )}
        </div>

        <aside className="page-grid__aside">
          <section className="sheet sheet--pad">
            <h2 className="aside-h">Lọc</h2>
            <div className="acct-filters">
              <label>
                <span className="field__label">Tìm theo tên, email hoặc mã học viên</span>
                <input className="field__input" value={search} onChange={(e) => setSearch(e.target.value)} />
              </label>
              <label>
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
          </section>

          <section className="sheet sheet--pad">
            <h2 className="aside-h">Tổng quan</h2>
            <dl className="acct-idx">
              {statusCounts.map(({ status, count }) => (
                <div key={status} className="acct-idx__row">
                  <dt>{USER_STATUS_LABEL[status]}</dt>
                  <dd>{count}</dd>
                </div>
              ))}
              <div className="acct-idx__row acct-idx__row--sub">
                <dt>Vai trò</dt>
                <dd>
                  {roleCounts.map(({ role, count }) => (
                    <span key={role}>
                      {ROLE_LABEL[role]} <strong>{count}</strong>
                    </span>
                  ))}
                </dd>
              </div>
            </dl>
          </section>

          <section className="sheet sheet--pad">
            <h2 className="aside-h">Lưu ý</h2>
            <p className="appr-note">
              Khóa một tài khoản sẽ cắt mọi phiên đang mở của người đó. Gỡ vai trò có hiệu lực
              chậm nhất sau 15 phút — thời gian sống của access token; nếu cần chặn ngay thì khóa
              tài khoản.
            </p>
          </section>
        </aside>
      </div>
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
    <div className="acct-edit">
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
