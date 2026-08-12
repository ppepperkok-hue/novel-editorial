import { EmptyState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";

export default function MeetingsPage() {
  return (
    <>
      <PageHeader title="会议中心" desc="发起专题会议、围观讨论、查看纪要" />
      <EmptyState title="建设中" hint="会议中心页面将在后续阶段填充。" />
    </>
  );
}
