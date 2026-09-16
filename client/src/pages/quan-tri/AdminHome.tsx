import { useState } from 'react';
import { useSession } from '@/components/shared/SessionProvider';
import { HomeHero } from '@/components/shared/HomeHero';
import { FormsSection } from '@/components/dashboard/FormsSection';
import { RagSection } from '@/components/dashboard/RagSection';
import { DocumentsSection } from '@/components/dashboard/DocumentsSection';
import { ActivitySection } from '@/components/dashboard/ActivitySection';

export default function AdminHome() {
  const { user } = useSession();
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="stack">
      <div className="spread">
        <HomeHero name={user?.fullName ?? ''} subtitle="Quản trị viên" />
        <button type="button" className="btn btn--ghost" onClick={() => setRefreshKey((k) => k + 1)}>
          Làm mới
        </button>
      </div>

      <div className="dash-grid">
        <FormsSection refreshKey={refreshKey} />
        <RagSection refreshKey={refreshKey} />
        <DocumentsSection refreshKey={refreshKey} />
        <ActivitySection refreshKey={refreshKey} />
      </div>
    </div>
  );
}
