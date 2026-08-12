import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function CostPage() {
  return (
    <>
      <PageHeader title="成本中心" desc="API 花费与预算控制" />
      <EmptyState title="建设中" hint="成本中心页面将在后续阶段填充。" />
    </>
  );
}
