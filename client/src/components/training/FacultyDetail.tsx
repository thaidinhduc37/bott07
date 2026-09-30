import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { Metrics } from '@/components/shared/Metrics';
import { ApiError } from '@/services/api';
import {
  facultyApi,
  type FacultyOverview,
  type LecturerCandidate,
} from '@/services/faculty-api';
import { ConfirmDeleteDialog, TrainingDialog } from './Dialogs';

/**
 * Chi tiết khoa: giảng viên, môn học (phân công giảng viên), lớp.
 *
 * Mọi vai trò có quyền đọc (ADMIN / ACADEMIC_MANAGER / DEPARTMENT_HEAD) đều
 * thấy đủ ba khối; trưởng khoa chỉ vào được khoa của mình (backend chặn).
 */
export function FacultyDetail({ facultyId, onBack }: { facultyId: string; onBack?: () => void }) {
  const [data, setData] = useState<FacultyOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [courseFilter, setCourseFilter] = useState<'all' | 'unassigned'>('all');

  // Thêm giảng viên
  const addLecturerBtnRef = useRef<HTMLButtonElement>(null);
  const [showAddLecturer, setShowAddLecturer] = useState(false);

  // Bỏ giảng viên khỏi khoa
  const [toRemove, setToRemove] = useState<{ id: string; fullName: string; courseCount: number } | null>(null);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const removeBtnRef = useRef<HTMLButtonElement>(null);

  // Phân công giảng viên cho môn (inline)
  const [assigning, setAssigning] = useState<string | null>(null);
  const [assignError, setAssignError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await facultyApi.overview(facultyId);
      setData(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không tải được chi tiết khoa.');
    } finally {
      setLoading(false);
    }
  }, [facultyId]);

  useEffect(() => {
    void load();
  }, [load]);

  function flash(msg: string) {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 4000);
  }

  async function handleAssignLecturer(courseId: string, lecturerId: string) {
    setAssigning(courseId);
    setAssignError(null);
    try {
      await facultyApi.assignCourseLecturer(facultyId, courseId, lecturerId || null);
      flash('Đã cập nhật giảng viên.');
      void load();
    } catch (e) {
      setAssignError(e instanceof ApiError ? e.message : 'Không phân công được.');
    } finally {
      setAssigning(null);
    }
  }

  async function confirmRemoveLecturer() {
    if (!toRemove) return;
    setRemoving(true);
    setRemoveError(null);
    try {
      await facultyApi.removeLecturer(facultyId, toRemove.id);
      setToRemove(null);
      flash('Đã bỏ giảng viên khỏi khoa.');
      void load();
    } catch (e) {
      setRemoveError(e instanceof ApiError ? e.message : 'Không bỏ được giảng viên.');
    } finally {
      setRemoving(false);
    }
  }

  const visibleCourses = (data?.courses ?? []).filter((c) =>
    courseFilter === 'unassigned' ? !c.lecturer : true,
  );

  return (
    <div className="stack">
      {onBack && (
        <button type="button" className="btn btn--ghost btn--sm" onClick={onBack}>
          <Icon name="arrow" size={15} />
          Quay lại danh sách khoa
        </button>
      )}

      {notice && (
        <div className="notice notice--ok" role="status">
          {notice}
        </div>
      )}

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : data ? (
        <>
          <h2 className="train-detail__title">
            {data.faculty.code} — {data.faculty.name}
          </h2>

          <Metrics
            label="Số liệu khoa"
            items={[
              { label: 'Giảng viên', value: data.lecturers.length },
              { label: 'Môn học', value: data.courses.length },
              {
                label: 'Chưa phân công',
                value: data.unassignedCourseCount,
                tone: data.unassignedCourseCount > 0 ? 'warn' : 'ok',
              },
              { label: 'Học viên', value: data.faculty.studentCount },
            ]}
          />

          {/* ---- Giảng viên của khoa ---- */}
          <section className="sheet sheet--pad train-detail__section">
            <div className="section-head train-detail__head">
              <h3>Giảng viên của khoa</h3>
              <button
                ref={addLecturerBtnRef}
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setShowAddLecturer(true)}
              >
                <Icon name="plus" size={15} />
                Thêm giảng viên
              </button>
            </div>

            {data.lecturers.length === 0 ? (
              <p className="train-detail__empty">Chưa có giảng viên nào trong khoa.</p>
            ) : (
              <ul className="train-detail__list">
                {data.lecturers.map((l) => (
                  <li key={l.id} className="train-detail__row">
                    <div>
                      <span className="train-detail__name">{l.fullName}</span>
                      <span className="train-detail__sub mono">{l.email}</span>
                      <span className="train-detail__sub"> — {l.courseCount} môn</span>
                    </div>
                    <button
                      ref={l.id === data.lecturers[0].id ? removeBtnRef : undefined}
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => {
                        setRemoveError(null);
                        setToRemove({ id: l.id, fullName: l.fullName, courseCount: l.courseCount });
                      }}
                      aria-label={`Bỏ ${l.fullName} khỏi khoa`}
                    >
                      <Icon name="close" size={14} />
                      <span className="sr-only">Bỏ khỏi khoa</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* ---- Môn của khoa ---- */}
          <section className="sheet sheet--pad train-detail__section">
            <div className="section-head train-detail__head">
              <h3>Môn của khoa</h3>
              <div className="seg" role="group" aria-label="Lọc môn">
                <button
                  type="button"
                  className={`seg__opt${courseFilter === 'all' ? ' seg__opt--on' : ''}`}
                  onClick={() => setCourseFilter('all')}
                  aria-pressed={courseFilter === 'all'}
                >
                  Tất cả
                </button>
                <button
                  type="button"
                  className={`seg__opt${courseFilter === 'unassigned' ? ' seg__opt--on' : ''}`}
                  onClick={() => setCourseFilter('unassigned')}
                  aria-pressed={courseFilter === 'unassigned'}
                >
                  Chưa phân công ({data.unassignedCourseCount})
                </button>
              </div>
            </div>

            {visibleCourses.length === 0 ? (
              <p className="train-detail__empty">
                {courseFilter === 'unassigned' ? 'Tất cả môn đều đã có giảng viên.' : 'Chưa có môn nào trong khoa.'}
              </p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <caption>{visibleCourses.length} môn</caption>
                  <thead>
                    <tr>
                      <th>Mã</th>
                      <th>Tên môn</th>
                      <th className="num">Tín chỉ</th>
                      <th>Giảng viên phụ trách</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleCourses.map((c) => (
                      <tr key={c.id}>
                        <td className="mono">{c.code}</td>
                        <td>{c.name}</td>
                        <td className="num">{c.credits}</td>
                        <td>
                          <select
                            className="field__input train-detail__select"
                            value={c.lecturer?.id ?? ''}
                            disabled={assigning === c.id}
                            onChange={(e) => void handleAssignLecturer(c.id, e.target.value)}
                            aria-label={`Giảng viên phụ trách môn ${c.code}`}
                          >
                            <option value="">— Chưa phân công —</option>
                            {data.lecturers.map((l) => (
                              <option key={l.id} value={l.id}>
                                {l.fullName}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {assignError && (
              <p className="notice notice--error" role="alert">
                {assignError}
              </p>
            )}
          </section>

          {/* ---- Lớp của khoa ---- */}
          <section className="sheet sheet--pad train-detail__section">
            <div className="section-head train-detail__head">
              <h3>Lớp của khoa</h3>
            </div>

            {data.classes.length === 0 ? (
              <p className="train-detail__empty">Chưa có lớp nào thuộc khoa này.</p>
            ) : (
              <ul className="train-detail__list">
                {data.classes.map((c) => (
                  <li key={c.id} className="train-detail__row">
                    <div>
                      <span className="train-detail__name mono">{c.code}</span>
                      <span className="train-detail__sub"> — {c.name}</span>
                    </div>
                    <div className="train-detail__meta">
                      {c.cohortYear && <span className="tag tag--muted">Khóa {c.cohortYear}</span>}
                      <span className="train-detail__sub">{c.studentCount} học viên</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}

      {/* Hộp thoại thêm giảng viên */}
      {showAddLecturer && (
        <AddLecturerDialog
          facultyId={facultyId}
          openRef={addLecturerBtnRef}
          onClose={() => setShowAddLecturer(false)}
          onSaved={() => {
            setShowAddLecturer(false);
            flash('Đã thêm giảng viên vào khoa.');
            void load();
          }}
        />
      )}

      {/* Hộp thoại xác nhận bỏ giảng viên */}
      {toRemove && (
        <ConfirmDeleteDialog
          openRef={removeBtnRef}
          title="Bỏ giảng viên khỏi khoa"
          message={`Bỏ ${toRemove.fullName} khỏi khoa?${toRemove.courseCount > 0 ? ` Sẽ bỏ phân công ${toRemove.courseCount} môn.` : ''}`}
          busy={removing}
          error={removeError}
          onConfirm={() => void confirmRemoveLecturer()}
          onClose={() => setToRemove(null)}
        />
      )}
    </div>
  );
}

/**
 * Hộp thoại chọn giảng viên từ danh sách ứng viên (chưa thuộc khoa nào hoặc
 * đã thuộc khoa này) để thêm vào khoa.
 */
function AddLecturerDialog({
  facultyId,
  openRef,
  onClose,
  onSaved,
}: {
  facultyId: string;
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [candidates, setCandidates] = useState<LecturerCandidate[]>([]);
  const [selected, setSelected] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    facultyApi
      .lecturerCandidates()
      .then((r) => setCandidates(r.items))
      .catch(() => setCandidates([]));
  }, []);

  async function submit() {
    if (!selected || saving) return;
    setSaving(true);
    setError(null);
    try {
      await facultyApi.addLecturer(facultyId, selected);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không thêm được giảng viên.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <TrainingDialog
      openRef={openRef}
      title="Thêm giảng viên vào khoa"
      titleId="train-add-lecturer-title"
      onClose={onClose}
      forwardRef={dialogRef}
    >
      <div className="field">
        <label className="field__label" htmlFor="train-add-lecturer-select">
          Giảng viên
        </label>
        <select
          id="train-add-lecturer-select"
          className="field__input"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">— Chọn giảng viên —</option>
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>
              {c.fullName}
              {c.facultyName ? ` (${c.facultyName})` : ' (chưa có khoa)'}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}

      <div className="train-dlg__actions">
        <button
          type="button"
          className="btn btn--primary"
          disabled={saving || !selected}
          onClick={() => void submit()}
        >
          {saving ? 'Đang lưu…' : 'Thêm'}
        </button>
        <button type="button" className="btn btn--ghost" disabled={saving} onClick={onClose}>
          Hủy
        </button>
      </div>
    </TrainingDialog>
  );
}
