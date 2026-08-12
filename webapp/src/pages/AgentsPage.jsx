import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function AgentsPage() {
  return (
    <>
      <PageHeader title="Agent 管理" desc="人格档案、模型参数与写作模式" />
      <EmptyState title="建设中" hint="Agent 管理页面将在后续阶段填充。" />
    </>
  );
}
