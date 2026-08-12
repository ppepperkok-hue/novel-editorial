import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function WorksPage() {
  return (
    <>
      <PageHeader title="作品库" desc="每个项目的完整设定：大纲、角色与世界规则" />
      <EmptyState title="建设中" hint="作品库页面将在后续阶段填充。" />
    </>
  );
}
