import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Metrics } from '@/components/shared/Metrics';
import { PageHeader } from '@/components/shared/PageHeader';
import { dayLabel, hhmm } from '@/components/study/format';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { API_URL, ApiError } from '@/services/api';
import { teachingApi, type TeachingClass, type TeachingClassDetail } from '@/services/teaching-api';
import '@/styles/my-classes.css';

const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Không tải được dữ liệu');

/** Chuẩn hóa để lọc không phân biệt hoa thường và dấu. */
const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase();

const dateOf = (iso: string) => dayLabel(iso.slice(0, 10));

function ClassList() {
  const [items, setItems] = useState<TeachingClass[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    teachingApi
      .classes()
      .then((r) => setItems(r.items))
      .catch((e) => setError(errText(e)));
  }, []);

  if (error) {
    return (
      <div className="notice notice--error" role="alert">
        {error}
      </div>
    );
  }
  if (items === null) return <p className="eyebrow">Đang tải…</p>;
  if (items.length === 0) {
    return (
      <div className="empty">
        <p className="empty__title">Bạn chưa phụ trách lớp nào</p>
        <p>Lớp xuất hiện ở đây khi bạn được gán làm giảng viên của một môn đã có lịch học.</p>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Lớp</th>
            <th>Môn bạn dạy</th>
            <th>Học viên</th>
            <th>Buổi tới</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id}>
              <td>
                <Link to={`?lop=${c.id}`} className="mc-link">
                  {c.code}
                </Link>
                <div className="mc-sub">{c.name}</div>
              </td>
              <td>
                {c.courses.map((k) => (
                  <div key={k.id}>
                    <span className="mono">{k.code}</span> {k.name}
                  </div>
                ))}
              </td>
              <td style={{ whiteSpace: 'nowrap' }}>{c.studentCount}</td>
              <td style={{ whiteSpace: 'nowrap' }}>{c.nextSessionAt ? dateOf(c.nextSessionAt) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClassDetail({ id }: { id: string }) {
  const [data, setData] = useState<TeachingClassDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');

  useEffect(() => {
    setData(null);
    teachingApi
      .classDetail(id)
      .then(setData)
      .catch((e) => setError(errText(e)));
  }, [id]);

  const students = useMemo(() => {
    const needle = fold(q.trim());
    return (data?.students ?? []).filter((s) => !needle || fold(`${s.studentCode} ${s.fullName}`).includes(needle));
  }, [data, q]);

  useDocumentTitle(data ? `Lớp ${data.class.code}` : 'Lớp của tôi');

  if (error) {
    return (
      <>
        <PageHeader
          breadcrumb={[{ label: 'Lớp của tôi', to: '/can-bo/lop' }, { label: 'Không tìm thấy' }]}
          title="Lớp của tôi"
        />
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      </>
    );
  }
  if (!data) return <p className="eyebrow">Đang tải…</p>;

  const next = data.upcoming[0];
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: 'Lớp của tôi', to: '/can-bo/lop' }, { label: data.class.code }]}
        eyebrow="Giảng dạy"
        title={`Lớp ${data.class.code}`}
        description={[data.class.name, data.class.faculty].filter(Boolean).join(' · ')}
        actions={
          <>
            <a href={`${API_URL}/teaching/classes/${data.class.id}/export`} className="btn btn--quiet">
              Tải danh sách (CSV)
            </a>
            <Link to="/can-bo/nhap-diem" className="btn btn--quiet">
              Nhập điểm
            </Link>
            <Link to="/can-bo/lich" className="btn btn--quiet">
              Lịch dạy
            </Link>
          </>
        }
      />

      <Metrics
        label="Tóm tắt lớp"
        items={[
          { label: 'Học viên', value: data.students.length },
          { label: 'Môn bạn dạy', value: data.courses.length },
          {
            label: 'Buổi tới',
            value: next ? dateOf(next.startsAt) : '—',
            hint: next ? `${hhmm(next.startsAt)} · ${next.room}` : 'Không còn buổi nào',
          },
        ]}
      />

      <div className="page-grid">
        <div className="page-grid__main">
          <section className="sheet sheet--pad mc-roster">
            <div className="mc-roster__head">
              <h2 className="aside-h">Danh sách học viên</h2>
              <input
                type="search"
                className="field__input sub-search"
                placeholder="Lọc theo tên hoặc mã"
                aria-label="Lọc theo tên hoặc mã học viên"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            {students.length === 0 ? (
              <p className="home-aside__empty">
                {data.students.length === 0 ? 'Lớp chưa có học viên.' : 'Không có học viên nào khớp.'}
              </p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Mã học viên</th>
                      <th>Họ và tên</th>
                    </tr>
                  </thead>
                  <tbody>
                    {students.map((s) => (
                      <tr key={s.studentCode}>
                        <td className="mono">{s.studentCode}</td>
                        <td>{s.fullName}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mc-note">
              Việc xếp học viên vào lớp do phòng quản lý đào tạo thực hiện; giảng viên chỉ xem danh sách.
            </p>
          </section>
        </div>

        <aside className="page-grid__aside">
          <section className="sheet sheet--pad mc-card">
            <h2 className="aside-h">Môn bạn dạy</h2>
            <ul className="mc-list">
              {data.courses.map((k) => (
                <li key={k.id}>
                  <span className="mono">{k.code}</span> {k.name}
                  <span className="mc-sub"> · {k.credits} tín chỉ</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="sheet sheet--pad mc-card">
            <h2 className="aside-h">Buổi dạy sắp tới</h2>
            {data.upcoming.length === 0 ? (
              <p className="home-aside__empty">Không còn buổi dạy nào trong lịch.</p>
            ) : (
              <ul className="mc-list">
                {data.upcoming.map((s) => (
                  <li key={s.id}>
                    <strong>{dateOf(s.startsAt)}</strong> · {hhmm(s.startsAt)}
                    <div className="mc-sub">
                      {s.courseCode} · tiết {s.startPeriod}–{s.endPeriod} · {s.room}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}

/**
 * "Lớp của tôi": giảng viên xem các lớp có môn mình phụ trách và danh sách học viên (chỉ đọc).
 * Danh mục lớp và việc xếp học viên vào lớp vẫn là của quản lý đào tạo (trang Quản lý đào tạo).
 * Lớp đang xem nhớ trong `?lop=<id>`.
 */
export default function MyClasses() {
  useDocumentTitle('Lớp của tôi');
  const [params] = useSearchParams();
  const id = params.get('lop');

  return (
    <div className="stack">
      {id ? (
        <ClassDetail id={id} />
      ) : (
        <>
          <PageHeader eyebrow="Giảng dạy" title="Lớp của tôi" description="Các lớp có môn bạn phụ trách." />
          <ClassList />
        </>
      )}
    </div>
  );
}
