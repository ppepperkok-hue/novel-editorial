import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function ReaderPage() {
  return (
    <>
      <PageHeader title="阅读数据" desc="读者表现与反馈" />
      <EmptyState title="建设中" hint="阅读数据页面将在后续阶段填充。" />
    </>
  );
}
