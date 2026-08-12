import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="系统设置" desc="运行、预算、模型与风格" />
      <EmptyState title="建设中" hint="系统设置页面将在后续阶段填充。" />
    </>
  );
}
