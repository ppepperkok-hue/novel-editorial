import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function EditorialPage() {
  return (
    <>
      <PageHeader title="消息流" desc="编辑之间的协作消息与今日任务" />
      <EmptyState title="建设中" hint="消息流页面将在后续阶段填充。" />
    </>
  );
}
