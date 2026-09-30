import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ActivitySection } from '@/components/dashboard/ActivitySection';
import { DocumentsSection } from '@/components/dashboard/DocumentsSection';
import { FormsSection } from '@/components/dashboard/FormsSection';
import { RagSection } from '@/components/dashboard/RagSection';
import { pct } from '@/components/dashboard/format';
import { useDashboardSection } from '@/components/dashboard/useDashboardSection';
import { Metrics, type Metric } from '@/components/shared/Metrics';
import { PageHeader } from '@/components/shared/PageHeader';
import { useSession } from '@/components/shared/SessionProvider';
import { adminDashboardApi } from '@/services/admin-api';

interface Attention {
  text: string;
  to?: string;
}

export default function AdminHome() {
  const { user } = useSession();
  const [refreshKey, setRefreshKey] = useState(0);
  // Bốn nguồn tải độc lập một lần ở đây: phần tóm tắt trên cùng và bốn khối chi tiết
  // dùng chung kết quả, và một nguồn lỗi chỉ làm mất phần của nó.
  const forms = useDashboardSection(adminDashboardApi.forms, refreshKey);
  const rag = useDashboardSection(adminDashboardApi.rag, refreshKey);
  const docs = useDashboardSection(adminDashboardApi.documents, refreshKey);
  const activity = useDashboardSection(adminDashboardApi.activity, refreshKey);

  const metrics: Metric[] = [];
  const attention: Attention[] = [];

  if (activity.status === 'ok') {
    metrics.push({
      label: 'Người dùng hoạt động (7 ngày)',
      value: activity.data.activeUsers7d,
      hint: `${activity.data.activeUsers30d} trong 30 ngày`,
      to: '/quan-tri/tai-khoan',
    });
    const failed = activity.data.failedLogins7d.reduce((n, d) => n + d.count, 0);
    if (failed >= 10) {
      attention.push({ text: `${failed} lần đăng nhập thất bại trong 7 ngày qua`, to: '/quan-tri/nhat-ky' });
    }
  }
  if (forms.status === 'ok') {
    const waiting = forms.data.backlog.length;
    const longest = forms.data.backlog.reduce((n, b) => Math.max(n, b.daysWaiting), 0);
    metrics.push({
      label: 'Đơn tồn đọng',
      value: waiting,
      hint: waiting > 0 ? `lâu nhất ${longest} ngày` : 'Không có đơn nào',
      tone: waiting > 0 ? 'warn' : undefined,
    });
    if (longest >= 3) attention.push({ text: `Có đơn chờ xử lý đã ${longest} ngày` });
  }
  if (rag.status === 'ok') {
    metrics.push({
      label: 'Hỏi đáp bị từ chối trả lời',
      value: rag.data.abstentionRate === null ? '—' : `${pct(rag.data.abstentionRate)}%`,
      hint:
        rag.data.groundedFailureRate === null
          ? 'Chưa có dữ liệu kiểm chứng'
          : `${pct(rag.data.groundedFailureRate)}% câu không qua kiểm chứng`,
    });
    if (rag.data.groundedFailureRate !== null && rag.data.groundedFailureRate > 0.1) {
      attention.push({
        text: `${pct(rag.data.groundedFailureRate)}% câu trả lời không qua bước kiểm chứng nguồn`,
      });
    }
  }
  if (docs.status === 'ok') {
    const failed = docs.data.byIndexStatus.FAILED?.versions ?? 0;
    metrics.push({
      label: 'Tài liệu lập chỉ mục lỗi',
      value: failed,
      hint: failed > 0 ? 'Cần xử lý' : 'Không có tệp lỗi',
      to: '/quan-tri/tai-lieu',
      tone: failed > 0 ? 'warn' : 'ok',
    });
    if (failed > 0) attention.push({ text: `${failed} tệp tài liệu lập chỉ mục lỗi`, to: '/quan-tri/tai-lieu' });
    if (docs.data.ragConsistency !== 'in_sync') {
      attention.push({ text: `Chỉ mục tìm kiếm không khớp cơ sở dữ liệu (${docs.data.ragConsistency})`, to: '/quan-tri/tai-lieu' });
    }
  }

  const allLoaded = [forms, rag, docs, activity].every((s) => s.status !== 'loading');

  return (
    <div className="stack">
      <PageHeader
        title={`Chào ${user?.fullName ?? ''}`}
        description="Quản trị viên · tình hình vận hành hệ thống"
        actions={
          <button type="button" className="btn btn--ghost" onClick={() => setRefreshKey((k) => k + 1)}>
            Làm mới
          </button>
        }
      />

      {metrics.length > 0 && <Metrics label="Tóm tắt vận hành" items={metrics} />}

      {allLoaded && (
        <section className="sheet sheet--pad">
          <h2 className="aside-h">Cần chú ý</h2>
          {attention.length === 0 ? (
            <p className="home-aside__empty">Hiện không có gì bất thường.</p>
          ) : (
            <ul className="attn">
              {attention.map((a) => (
                <li key={a.text} className="attn__item">
                  <span>{a.text}</span>
                  {a.to && (
                    <Link to={a.to} className="attn__go">
                      Xem
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <div className="dash-grid">
        <FormsSection state={forms} />
        <RagSection state={rag} />
        <DocumentsSection state={docs} />
        <ActivitySection state={activity} />
      </div>
    </div>
  );
}
