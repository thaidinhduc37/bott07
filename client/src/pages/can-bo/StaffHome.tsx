import { useSession } from '@/components/shared/SessionProvider';
import { CardGrid, SectionCard } from '@/components/shared/SectionCard';

export default function StaffHome() {
  const { user } = useSession();
  const has = (r: string) => user?.roles.includes(r as never) ?? false;

  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-title">Chào {user?.fullName}</h1>
        <p className="page-sub">{user?.roleNames.join(' · ')}</p>
      </header>

      <CardGrid>
        {(has('APPROVER') || has('ACADEMIC_MANAGER')) && (
          <SectionCard
            href="/can-bo/don-cho-xu-ly"
            icon="inbox"
            title="Đơn chờ xử lý"
            description="Tiếp nhận, yêu cầu bổ sung, phê duyệt hoặc từ chối. Chỉ hiện những đơn đang ở đúng bước bạn phụ trách."
          />
        )}
        {(has('ACADEMIC_MANAGER') || has('LECTURER')) && (
          <SectionCard
            href="/can-bo/tai-lieu"
            icon="folder"
            title="Tài liệu"
            description="Nạp quy chế và giáo trình vào chỉ mục tìm kiếm. Theo dõi trạng thái lập chỉ mục của từng phiên bản."
          />
        )}
        {(has('ACADEMIC_MANAGER') || has('LECTURER')) && (
          <SectionCard
            href="/can-bo/lich"
            icon="calendar"
            title="Lịch học và lịch thi"
            description="Nhập lịch từ tệp CSV. Hệ thống báo lỗi theo từng dòng và cảnh báo trùng lớp, trùng phòng, trùng giảng viên."
          />
        )}
        <SectionCard
          href="/can-bo/hoi-dap"
          icon="chat"
          title="Hỏi đáp có trích dẫn"
          description="Tra cứu nhanh điều khoản quy chế khi xử lý đơn, kèm nguồn để dẫn lại cho học viên."
        />
      </CardGrid>
    </div>
  );
}
