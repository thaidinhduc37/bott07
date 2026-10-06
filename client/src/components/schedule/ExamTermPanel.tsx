import { useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/services/api';
import { scheduleApi, type MyExamTerm, type MyTerms } from '@/services/schedule-api';
import { ExamTable } from './ExamTable';

const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Không tải được lịch thi');

/**
 * Nội dung tab "Lịch thi": bộ lọc Năm học / Học kỳ (dựng từ các học kỳ của lớp học viên) và bảng kỳ thi.
 * Tab "Lịch học" bên cạnh không phụ thuộc bộ lọc này — nó giữ nguyên cách xem theo tuần.
 */
export function ExamTermPanel() {
  const [terms, setTerms] = useState<MyTerms | null>(null);
  const [year, setYear] = useState('');
  const [semester, setSemester] = useState('');
  const [data, setData] = useState<MyExamTerm | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    scheduleApi
      .myTerms()
      .then((t) => {
        setTerms(t);
        if (t.current) {
          setYear(t.current.academicYear);
          setSemester(t.current.semester);
        }
      })
      .catch((e) => {
        setError(errText(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!terms) return;
    if (terms.terms.length === 0) {
      setData(null);
      setLoading(false);
      return;
    }
    if (!year || !semester) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    scheduleApi
      .myExamTerm({ academicYear: year, semester })
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch((e) => {
        if (!cancelled) setError(errText(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [terms, year, semester]);

  const years = useMemo(() => [...new Set((terms?.terms ?? []).map((t) => t.academicYear))], [terms]);
  const semesters = useMemo(
    () => [...new Set((terms?.terms ?? []).filter((t) => t.academicYear === year).map((t) => t.semester))],
    [terms, year],
  );

  function changeYear(next: string) {
    setYear(next);
    // Giữ học kỳ nếu năm học mới cũng có, không thì lấy học kỳ đầu tiên của năm đó.
    const available = (terms?.terms ?? []).filter((t) => t.academicYear === next).map((t) => t.semester);
    setSemester(available.includes(semester) ? semester : (available[0] ?? ''));
  }

  return (
    <div className="stack">
      {terms && terms.terms.length > 0 && (
        <div className="sheet" style={{ padding: '0.75rem 1rem' }}>
          <div className="row" style={{ gap: 'var(--gap-4)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="field" style={{ minWidth: '10rem' }}>
              <label className="field__label" htmlFor="exam-year">
                Năm học
              </label>
              <select id="exam-year" className="field__input" value={year} onChange={(e) => changeYear(e.target.value)}>
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
            <div className="field" style={{ minWidth: '10rem' }}>
              <label className="field__label" htmlFor="exam-semester">
                Học kỳ
              </label>
              <select
                id="exam-semester"
                className="field__input"
                value={semester}
                onChange={(e) => setSemester(e.target.value)}
              >
                {semesters.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : !data || data.items.length === 0 ? (
        <div className="empty">
          <p className="empty__title">Chưa có lịch thi</p>
          <p>
            {terms && terms.terms.length === 0
              ? 'Tài khoản chưa gắn với lớp có lịch nên chưa có lịch thi.'
              : 'Học kỳ này chưa có lịch thi.'}
          </p>
        </div>
      ) : (
        <ExamTable
          examCount={data.examCount}
          upcomingCount={data.upcomingCount}
          totalCredits={data.totalCredits}
          items={data.items}
        />
      )}
    </div>
  );
}
