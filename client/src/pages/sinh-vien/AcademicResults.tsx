import { useEffect, useMemo, useState } from 'react';
import { Metrics } from '@/components/shared/Metrics';
import { PageHeader } from '@/components/shared/PageHeader';
import { viScore } from '@/components/study/format';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/services/api';
import { gradesApi, type AcademicResults, type GradeCourse, type GradeTerm } from '@/services/grades-api';

const ALL = 'all';

/** Điểm thành phần: số (dấu phẩy) khi có, "—" màu nhạt khi chưa nhập. */
function scoreCell(n: number | null) {
  return n === null ? <span className="grd-dash">—</span> : viScore(n);
}

/** Điểm học phần: thẻ đạt/không đạt, chữ thường khi chưa có điểm. */
function totalCell(c: GradeCourse) {
  if (c.total === null) return <span className="grd-dash">—</span>;
  const cls = c.passed === true ? 'tag--ok' : c.passed === false ? 'tag--seal' : '';
  return <span className={`grd-total${cls ? ` tag ${cls}` : ''}`}>{viScore(c.total)}</span>;
}

function TermSheet({ term }: { term: GradeTerm }) {
  return (
    <section className="sheet sheet--pad">
      <div className="section-head">
        <h2 className="aside-h">
          {term.semester} — Năm học {term.academicYear}
        </h2>
        <span className="grd-term-tags">
          <span className="tag tag--muted">
            {term.gradedCount}/{term.courseCount} môn có điểm
          </span>
          <span className="tag tag--muted">{term.credits} tín chỉ</span>
        </span>
      </div>

      <div className="table-wrap">
        <table className="data-table grd-table">
          <thead>
            <tr>
              <th className="num">STT</th>
              <th>Mã môn</th>
              <th>Tên môn</th>
              <th className="num">TC</th>
              <th className="num grd-col-part">TH</th>
              <th className="num grd-col-part">QT</th>
              <th className="num grd-col-part">GK</th>
              <th className="num grd-col-part">CK</th>
              <th className="num">Điểm</th>
            </tr>
          </thead>
          <tbody>
            {term.courses.map((c, i) => (
              <tr key={c.courseId}>
                <td className="num">{i + 1}</td>
                <td className="mono">{c.code}</td>
                <td>{c.name}</td>
                <td className="num">{c.credits}</td>
                <td className="num grd-col-part">{scoreCell(c.practice)}</td>
                <td className="num grd-col-part">{scoreCell(c.process)}</td>
                <td className="num grd-col-part">{scoreCell(c.midterm)}</td>
                <td className="num grd-col-part">{scoreCell(c.finalExam)}</td>
                <td className="num">{totalCell(c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="grd-term-gpa">
        Điểm trung bình học kỳ:{' '}
        <strong>{term.gpa === null ? '—' : viScore(term.gpa)}</strong>
      </p>
    </section>
  );
}

export default function AcademicResults() {
  useDocumentTitle('Kết quả học tập');
  const [data, setData] = useState<AcademicResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [termFilter, setTermFilter] = useState(ALL);

  useEffect(() => {
    gradesApi
      .me()
      .then((r) => {
        setData(r);
        if (r.terms.length > 0) setTermFilter(`${r.terms[0].academicYear}|${r.terms[0].semester}`);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Không tải được kết quả học tập'));
  }, []);

  const terms = data?.terms ?? [];
  const visible = useMemo(
    () => (termFilter === ALL ? terms : terms.filter((t) => `${t.academicYear}|${t.semester}` === termFilter)),
    [terms, termFilter],
  );

  return (
    <div className="stack">
      <PageHeader title="Kết quả học tập" description="Điểm học phần theo từng học kỳ." />

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {!data && !error && <p className="eyebrow">Đang tải…</p>}

      {data && (
        <>
          <Metrics
            label="Tổng kết"
            items={[
              {
                label: 'Tín chỉ đã học',
                value: data.summary.creditsStudied,
                hint: 'môn đã có điểm',
              },
              {
                label: 'Tín chỉ tích lũy',
                value: data.summary.creditsEarned,
                hint: `môn đạt từ ${viScore(data.passScore)}`,
              },
              {
                label: 'Điểm TB chung',
                value: data.summary.gpa === null ? '—' : viScore(data.summary.gpa),
              },
              {
                label: 'Điểm TB tích lũy',
                value: data.summary.gpaEarned === null ? '—' : viScore(data.summary.gpaEarned),
                hint: 'chỉ tính môn đạt',
              },
            ]}
          />
          <p className="grd-note">Thang điểm 10. Điểm học phần do giảng viên / phòng đào tạo nhập.</p>

          {terms.length === 0 ? (
            <div className="empty">
              <p className="empty__title">Chưa có dữ liệu học kỳ nào</p>
              <p>Tài khoản chưa gắn với lớp hoặc lớp chưa có lịch học.</p>
            </div>
          ) : (
            <>
              <div className="grd-filter">
                <label className="field__label" htmlFor="grd-term">
                  Học kỳ
                </label>
                <select
                  id="grd-term"
                  className="field__input"
                  value={termFilter}
                  onChange={(e) => setTermFilter(e.target.value)}
                >
                  <option value={ALL}>Tất cả học kỳ</option>
                  {terms.map((t) => (
                    <option key={`${t.academicYear}|${t.semester}`} value={`${t.academicYear}|${t.semester}`}>
                      {t.semester} — Năm học {t.academicYear}
                    </option>
                  ))}
                </select>
              </div>

              {visible.map((t) => (
                <TermSheet key={`${t.academicYear}|${t.semester}`} term={t} />
              ))}
            </>
          )}
        </>
      )}
    </div>
  );
}
