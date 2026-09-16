import { Link } from 'react-router-dom';
import { useSession } from '@/components/shared/SessionProvider';
import { CardGrid, SectionCard } from '@/components/shared/SectionCard';

export default function StudentHome() {
  const { user } = useSession();
  const profile = user?.studentProfile;

  return (
    <div className="stack shell--full">
      <header className="page-head">
        <h1 className="page-title">Chào {user?.fullName}</h1>
        {profile && (
          <p className="page-sub">
            <span className="mono">{profile.studentCode}</span>
            {profile.studyClass && <> · Lớp {profile.studyClass.code}</>}
            {profile.cohort && <> · Khóa {profile.cohort}</>}
            {profile.trainingSystem && <> · {profile.trainingSystem}</>}
          </p>
        )}
      </header>

      <CardGrid>
        <SectionCard
          href="/sinh-vien/hoi-dap"
          icon="chat"
          title="Hỏi đáp"
          description="Hỏi về quy chế học tập hoặc giáo trình môn học. Mỗi câu trả lời kèm nguồn để đối chiếu."
        />
        <SectionCard
          href="/sinh-vien/lich"
          icon="calendar"
          title="Lịch học và lịch thi"
          description="Xem lịch theo tuần, lọc theo môn học, kèm phòng thi và tài liệu được mang vào."
        />
        <SectionCard
          href="/sinh-vien/bieu-mau"
          icon="form"
          title="Lập đơn và trình ký"
          description="Hệ thống điền sẵn thông tin từ hồ sơ, bạn chỉ nhập phần còn thiếu, ký điện tử nội bộ rồi gửi duyệt."
        />
      </CardGrid>

      <section className="sheet sheet--pad">
        <h2 className="display" style={{ fontSize: '1.15rem', margin: 0 }}>
          Thông tin dùng để điền đơn
        </h2>
        <p className="prose" style={{ marginTop: 'var(--gap-3)' }}>
          Khi bạn lập đơn, hệ thống lấy họ tên, mã học viên, lớp, khóa, hệ đào tạo và ngày sinh từ
          hồ sơ này. Nếu có thông tin sai, báo Phòng Quản lý học viên — bạn không tự sửa được những
          trường đó, và đó là điều đúng: đơn đã ký phải khớp với dữ liệu học vụ.
        </p>
        <p style={{ marginTop: 'var(--gap-5)', marginBottom: 0 }}>
          <Link to="/ho-so" className="btn btn--ghost">
            Xem hồ sơ của tôi
          </Link>
        </p>
      </section>
    </div>
  );
}
