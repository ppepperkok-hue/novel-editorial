import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function ExecutionsPage() {
  return (
    <>
      <PageHeader title="执行记录" desc="每次运行的完整留痕与失败详情" />
      <EmptyState title="建设中" hint="执行记录页面将在后续阶段填充。" />
    </>
  );
}
