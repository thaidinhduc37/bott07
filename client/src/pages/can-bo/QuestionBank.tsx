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
type Format = 'gift' | 'csv';

const COLUMNS = 'cau_hoi,a,b,c,d,dap_an,giai_thich,chuong';
const EXAMPLE = 'Thủ đô của Việt Nam là?,Hà Nội,Huế,Đà Nẵng,Cần Thơ,A,Hà Nội là thủ đô từ năm 1010,Chương 1';
const LETTERS = 'ABCDEFGHIJ';

// Mẫu GIFT (định dạng của Moodle): mỗi câu cách nhau một dòng trống; = đáp án đúng, ~ đáp án sai, # phản hồi.
const GIFT_SAMPLE = `// Dòng bắt đầu bằng // là ghi chú. Số đáp án tùy ý.
$CATEGORY: Chương 1

Thủ đô của Việt Nam là {
=Hà Nội#Hà Nội là thủ đô từ năm 1010
~Huế
~Đà Nẵng
~Cần Thơ
}

Mã hóa đối xứng dùng cùng một khóa để mã và giải mã. {T}

Chọn các số chẵn {
=2
=4
~3
~5
}
`;
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
                <li key={i} className={q.correctIndexes.includes(i) ? 'qb-opt qb-opt--ok' : 'qb-opt'}>
                  <span className="qb-opt__k">{LETTERS[i]}</span>
                  {o}
                </li>
              ))}
            </ul>
            <p className="qb-item__meta">
              {q.correctIndexes.length > 1 && <span className="tag tag--muted">Nhiều đáp án đúng</span>}
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
  const [format, setFormat] = useState<Format>('gift');
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
                { id: 'import', label: 'Nhập từ tệp' },
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
              <div className="stack">
                <div className="field">
                  <span className="field__label" id="qb-format-label">
                    Định dạng tệp
                  </span>
                  <fieldset
                    className="seg"
                    style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
                    aria-labelledby="qb-format-label"
                  >
                    <legend className="sr-only">Định dạng tệp</legend>
                    {(
                      [
                        ['gift', 'GIFT (Moodle)'],
                        ['csv', 'CSV (Excel)'],
                      ] as const
                    ).map(([id, label]) => (
                      <label key={id} className={`seg__opt${format === id ? ' seg__opt--on' : ''}`}>
                        <input type="radio" name="qb-format" checked={format === id} onChange={() => setFormat(id)} />
                        {label}
                      </label>
                    ))}
                  </fieldset>
                </div>
                {format === 'gift' ? (
                  <CsvImport
                    key={`${course.id}-gift`}
                    id="qb-file"
                    run={(file, dryRun) => questionBankApi.import(course.id, file, dryRun, 'gift')}
                    accept=".gift,.txt,text/plain"
                    fileLabel="Tệp GIFT"
                    hint="Tệp văn bản UTF-8 (.gift hoặc .txt) — xuất từ Moodle hoặc tự soạn. Bấm “Kiểm tra” trước khi nhập."
                    formatGuide={
                      <>
                        <p className="field__hint" style={{ margin: '0 0 var(--gap-2)' }}>
                          Mỗi câu cách nhau một dòng trống:
                        </p>
                        <pre className="gent-cols qb-gift">{GIFT_SAMPLE}</pre>
                      </>
                    }
                    sample={GIFT_SAMPLE}
                    sampleName="mau-cau-hoi.gift"
                    submitLabel={`Nhập vào ${course.code}`}
                    notes={[
                      '= đáp án đúng, ~ đáp án sai; số đáp án tùy ý (2 đến 10). Nhiều dấu = hoặc ~%50%A ~%50%B là câu nhiều đáp án đúng: học viên phải chọn đủ và đúng.',
                      '{T} hoặc {F} cho câu đúng/sai. # sau đáp án là phản hồi; #### cuối khối là lời giải chung (hiện sau khi học viên nộp bài).',
                      '$CATEGORY: tên → chương của các câu phía sau. Dạng chưa hỗ trợ (trả lời ngắn, ghép cặp, số, tự luận) sẽ báo lỗi ở đúng câu.',
                      'Câu trùng với câu đã có được bỏ qua. Còn câu lỗi thì không ghi gì. Một tệp tối đa 500 câu; mỗi môn tối đa 2.000 câu.',
                    ]}
                    onAccepted={loadCourses}
                  />
                ) : (
                  <CsvImport
                    key={`${course.id}-csv`}
                    id="qb-file"
                    run={(file, dryRun) => questionBankApi.import(course.id, file, dryRun, 'csv')}
                    columns={COLUMNS}
                    exampleRow={EXAMPLE}
                    sample={`${COLUMNS}
${EXAMPLE}
`}
                    sampleName="mau-cau-hoi.csv"
                    submitLabel={`Nhập vào ${course.code}`}
                    notes={[
                      'cau_hoi, a, b, dap_an bắt buộc; c–j là đáp án thêm (tối đa 10, phải liền nhau).',
                      'dap_an là chữ cái của đáp án đúng (B); nhiều đáp án đúng thì ghi A,C (đặt trong dấu nháy kép khi có dấu phẩy). Để trống giai_thich thì hệ thống ghi sẵn đáp án đúng.',
                      'Câu trùng với câu đã có được bỏ qua. Còn dòng lỗi thì không ghi gì. Soạn trong Excel rồi Lưu thành → CSV UTF-8.',
                    ]}
                    onAccepted={loadCourses}
                  />
                )}
              </div>
            )}
          </TabPanel>
        </>
      )}
    </div>
  );
}
