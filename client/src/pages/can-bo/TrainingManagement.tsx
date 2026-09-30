import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/shared/PageHeader';
import { TabPanel, Tabs } from '@/components/shared/Tabs';
import { useSession } from '@/components/shared/SessionProvider';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ClassesPanel } from '@/components/training/ClassesPanel';
import { CoursesPanel } from '@/components/training/CoursesPanel';
import { StudentsPanel } from '@/components/training/StudentsPanel';
import { FacultiesPanel } from '@/components/training/FacultiesPanel';
import { FacultyDetail } from '@/components/training/FacultyDetail';
import { RoomsPanel } from '@/components/training/RoomsPanel';
import { facultyApi } from '@/services/faculty-api';
import '@/styles/training.css';

type Tab = 'khoa' | 'lop' | 'mon' | 'hoc-vien' | 'phong';

const TABS: { id: Tab; label: string }[] = [
  { id: 'khoa', label: 'Khoa' },
  { id: 'lop', label: 'Lớp' },
  { id: 'mon', label: 'Môn học' },
  { id: 'hoc-vien', label: 'Học viên' },
  { id: 'phong', label: 'Phòng học' },
];

/**
 * Trưởng khoa chỉ có một khoa để quản lý nên không cần danh sách: vào thẳng chi tiết khoa của mình
 * (chỉ xem và phân công; thêm/sửa/xóa khoa là việc của quản lý đào tạo và quản trị).
 */
function MyFaculty() {
  const [id, setId] = useState<string | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    facultyApi
      .list()
      .then((r) => setId(r.items[0]?.id ?? null))
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="notice notice--error" role="alert">
        {error}
      </div>
    );
  }
  if (id === undefined) return <p className="eyebrow">Đang tải…</p>;
  if (id === null) {
    return (
      <div className="empty">
        <p className="empty__title">Bạn chưa được phân công phụ trách khoa nào</p>
        <p>Liên hệ cán bộ quản lý đào tạo để được gán làm trưởng khoa.</p>
      </div>
    );
  }
  return <FacultyDetail facultyId={id} />;
}

/**
 * Trang "Quản lý đào tạo".
 *
 * ADMIN / ACADEMIC_MANAGER: đủ 5 tab.
 * DEPARTMENT_HEAD (không có 2 vai trên): chỉ thấy tab "Khoa" (không thanh tab),
 * tiêu đề "Khoa của tôi", chỉ xem/phân công trong khoa mình.
 *
 * Tab được nhớ trong `?tab=` (mặc định `khoa`); chi tiết khoa qua `?khoa=<id>`.
 */
export default function TrainingManagement() {
  useDocumentTitle('Quản lý đào tạo');
  const [params, setParams] = useSearchParams();
  const { user } = useSession();

  const roles = user?.roles ?? [];
  const isManager = roles.includes('ADMIN') || roles.includes('ACADEMIC_MANAGER');
  const isDeptHeadOnly = !isManager && roles.includes('DEPARTMENT_HEAD');

  const raw = params.get('tab');
  const tab: Tab = isDeptHeadOnly
    ? 'khoa'
    : raw === 'lop' || raw === 'mon' || raw === 'hoc-vien' || raw === 'phong'
      ? raw
      : 'khoa';

  const facultyId = params.get('khoa') ?? undefined;
  const classFilter = tab === 'hoc-vien' ? params.get('lop') ?? undefined : undefined;

  function changeTab(next: Tab) {
    const p = new URLSearchParams(params);
    p.set('tab', next);
    p.delete('lop');
    p.delete('khoa');
    setParams(p, { replace: true });
  }

  function openFacultyDetail(id: string) {
    const p = new URLSearchParams(params);
    p.set('tab', 'khoa');
    p.set('khoa', id);
    setParams(p, { replace: true });
  }

  function closeFacultyDetail() {
    const p = new URLSearchParams(params);
    p.delete('khoa');
    setParams(p, { replace: true });
  }

  function showStudentsOf(classId: string) {
    const p = new URLSearchParams(params);
    p.set('tab', 'hoc-vien');
    p.set('lop', classId);
    setParams(p, { replace: true });
  }

  // Trưởng khoa: không thanh tab, chỉ nội dung khoa.
  if (isDeptHeadOnly) {
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Học vụ"
          title="Khoa của tôi"
          description="Xem và phân công trong phạm vi khoa mình phụ trách."
        />
        <MyFaculty />
      </div>
    );
  }

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Học vụ"
        title="Quản lý đào tạo"
        description="Quản lý khoa, lớp, môn học và việc xếp học viên vào lớp."
        tabs={
          <Tabs
            label="Nội dung trang Quản lý đào tạo"
            idPrefix="dao-tao"
            value={tab}
            onChange={changeTab}
            items={TABS}
          />
        }
      />

      <TabPanel idPrefix="dao-tao" tab={tab}>
        {tab === 'khoa' &&
          (facultyId ? (
            <FacultyDetail facultyId={facultyId} onBack={closeFacultyDetail} />
          ) : (
            <FacultiesPanel onOpenDetail={openFacultyDetail} />
          ))}
        {tab === 'lop' && <ClassesPanel onShowStudents={showStudentsOf} />}
        {tab === 'mon' && <CoursesPanel />}
        {tab === 'hoc-vien' && <StudentsPanel initialClassId={classFilter} />}
        {tab === 'phong' && (isManager ? <RoomsPanel /> : null)}
      </TabPanel>
    </div>
  );
}
