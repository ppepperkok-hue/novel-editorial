import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function FlowPage() {
  return (
    <>
      <PageHeader title="链路" desc="调度全链路拓扑，不运行也能人工审查" />
      <EmptyState title="建设中" hint="链路页面将在后续阶段填充。" />
    </>
  );
}
