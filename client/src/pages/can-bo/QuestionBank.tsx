import { useCallback, useEffect, useState } from 'react';
import { CsvImport } from '@/components/shared/CsvImport';
import { Icon } from '@/components/shared/Icon';
import { PageHeader } from '@/components/shared/PageHeader';
import { TabPanel, Tabs } from '@/components/shared/Tabs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/services/api';
import { questionBankApi, type BankCourse, type BankQuestion } from '@/services/question-bank-api';
import '@/styles/question-bank.css';

type Part = 'list' | 'import';

const COLUMNS = 'cau_hoi,a,b,c,d,dap_an,giai_thich,chuong';
const EXAMPLE = 'Thủ đô của Việt Nam là?,Hà Nội,Huế,Đà Nẵng,Cần Thơ,A,Hà Nội là thủ đô từ năm 1010,Chương 1';
const LETTERS = 'ABCDEF';
const PAGE_SIZE = 20;

const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

function QuestionList({ course, onChanged }: { course: BankCourse; onChanged: () => void }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ total: number; items: BankQuestion[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    questionBankApi
      .questions(course.id, page, PAGE_SIZE)
      .then(setData)
      .catch((e) => setError(errText(e, 'Không tải được câu hỏi')));
  }, [course.id, page]);

  useEffect(() => {
    load();
  }, [load]);

  async function remove(q: BankQuestion) {
    if (!window.confirm('Xóa câu hỏi này khỏi ngân hàng?')) return;
    setBusyId(q.id);
    try {
      await questionBankApi.remove(q.id);
      // Xóa hết câu cuối của trang thì lùi một trang.
      if (data && data.items.length === 1 && page > 1) setPage(page - 1);
      else load();
      onChanged();
    } catch (e) {
      setError(errText(e, 'Không xóa được câu hỏi'));
    } finally {
      setBusyId(null);
    }
  }

  if (error) {
    return (
      <div className="notice notice--error" role="alert">
        {error}
      </div>
    );
  }
  if (!data) return <p className="eyebrow">Đang tải…</p>;
  if (data.total === 0) {
    return (
      <div className="empty">
        <p className="empty__title">Môn này chưa có câu hỏi</p>
        <p>Chuyển sang “Nhập từ CSV” để thêm câu hỏi của bạn.</p>
      </div>
    );
  }

  const pages = Math.ceil(data.total / PAGE_SIZE);
  return (
    <div className="stack">
      <ol className="qb-list" start={(page - 1) * PAGE_SIZE + 1}>
        {data.items.map((q) => (
          <li key={q.id} className="qb-item sheet">
            <div className="qb-item__head">
              <p className="qb-item__q">{q.question}</p>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => void remove(q)}
                disabled={busyId === q.id}
                aria-label="Xóa câu hỏi"
              >
                <Icon name="trash" size={15} />
              </button>
            </div>
            <ul className="qb-opts">
              {q.options.map((o, i) => (
                <li key={i} className={i === q.correctIndex ? 'qb-opt qb-opt--ok' : 'qb-opt'}>
                  <span className="qb-opt__k">{LETTERS[i]}</span>
                  {o}
                </li>
              ))}
            </ul>
            <p className="qb-item__meta">
              {q.chapter && <span className="tag tag--muted">{q.chapter}</span>}
              <span>{q.explanation}</span>
            </p>
          </li>
        ))}
      </ol>
      {pages > 1 && (
        <div className="row qb-pager">
          <button type="button" className="btn btn--quiet" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Trang trước
          </button>
          <span className="field__hint">
            Trang {page} / {pages}
          </span>
          <button type="button" className="btn btn--quiet" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Trang sau
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Ngân hàng câu hỏi: giảng viên nhập câu trắc nghiệm của mình (CSV) cho môn mình phụ trách; học viên ôn tập
 * có thể rút ngẫu nhiên từ đây thay vì để AI sinh. Quản lý đào tạo / quản trị thấy mọi môn.
 */
export default function QuestionBank() {
  useDocumentTitle('Ngân hàng câu hỏi');
  const [courses, setCourses] = useState<BankCourse[] | null>(null);
  const [courseId, setCourseId] = useState('');
  const [part, setPart] = useState<Part>('list');
  const [error, setError] = useState<string | null>(null);

  const loadCourses = useCallback(() => {
    questionBankApi
      .courses()
      .then((r) => {
        setCourses(r.items);
        setCourseId((cur) => cur || r.items[0]?.id || '');
      })
      .catch((e) => setError(errText(e, 'Không tải được danh sách môn')));
  }, []);

  useEffect(() => {
    loadCourses();
  }, [loadCourses]);

  const course = courses?.find((c) => c.id === courseId);

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Giảng dạy"
        title="Ngân hàng câu hỏi"
        description="Câu trắc nghiệm của bạn cho từng môn; học viên ôn tập rút ngẫu nhiên từ đây."
        tabs={
          course ? (
            <Tabs
              label="Nội dung trang Ngân hàng câu hỏi"
              idPrefix="ngan-hang"
              value={part}
              onChange={setPart}
              items={[
                { id: 'list', label: 'Câu hỏi', badge: course.questionCount },
                { id: 'import', label: 'Nhập từ CSV' },
              ]}
            />
          ) : undefined
        }
      />

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}
      {courses === null && !error && <p className="eyebrow">Đang tải…</p>}
      {courses !== null && courses.length === 0 && (
        <div className="empty">
          <p className="empty__title">Bạn chưa phụ trách môn nào</p>
          <p>Ngân hàng câu hỏi gắn với môn bạn được phân công giảng dạy.</p>
        </div>
      )}

      {course && courses && (
        <>
          <div className="sheet qb-bar">
            <label className="field__label" htmlFor="qb-course">
              Môn học
            </label>
            <select
              id="qb-course"
              className="field__input qb-bar__select"
              value={courseId}
              onChange={(e) => setCourseId(e.target.value)}
            >
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name} ({c.questionCount} câu)
                </option>
              ))}
            </select>
          </div>

          <TabPanel idPrefix="ngan-hang" tab={part}>
            {part === 'list' ? (
              <QuestionList key={course.id} course={course} onChanged={loadCourses} />
            ) : (
              <CsvImport
                key={course.id}
                id="qb-file"
                run={(file, dryRun) => questionBankApi.import(course.id, file, dryRun)}
                columns={COLUMNS}
                exampleRow={EXAMPLE}
                sample={`${COLUMNS}\n${EXAMPLE}\n`}
                sampleName="mau-cau-hoi.csv"
                submitLabel={`Nhập vào ${course.code}`}
                notes={[
                  'cau_hoi, a, b, dap_an bắt buộc; c–f là đáp án thêm (tối đa 6, phải liền nhau).',
                  'dap_an là chữ cái của đáp án đúng (A, B, C…). Để trống giai_thich thì hệ thống ghi sẵn đáp án đúng.',
                  'Câu trùng với câu đã có (cùng nội dung và đáp án) được bỏ qua, không báo lỗi.',
                  'Còn dòng lỗi thì không ghi gì. Một tệp tối đa 500 dòng; mỗi môn tối đa 2.000 câu.',
                  'Soạn trong Excel rồi chọn Lưu thành → CSV UTF-8.',
                ]}
                onAccepted={loadCourses}
              />
            )}
          </TabPanel>
        </>
      )}
    </div>
  );
}
