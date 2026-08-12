import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function ChaptersPage() {
  return (
    <>
      <PageHeader title="章节管理" desc="全部章节的写作状态、质量分与发布进度" />
      <EmptyState title="建设中" hint="章节管理页面将在后续阶段填充。" />
    </>
  );
}
