import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="仪表盘" desc="编辑部现在的状态，和需要您留意的事" />
      <EmptyState title="建设中" hint="首页工作台将在后续阶段填充。" />
    </>
  );
}
