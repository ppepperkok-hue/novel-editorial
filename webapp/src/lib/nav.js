import {
  BookOpen,
  ChartLineUp,
  ChatCircleDots,
  ClockCounterClockwise,
  Coins,
  EnvelopeSimple,
  FlowArrow,
  Gauge,
  GearSix,
  ListDashes,
  Scroll,
  UsersThree,
} from "@phosphor-icons/react";

/** 五区两级导航配置。@stable */
export const NAV_GROUPS = [
  {
    id: "overview",
    label: "总览",
    items: [{ id: "dashboard", label: "仪表盘", icon: Gauge }],
  },
  {
    id: "editorial",
    label: "编辑部",
    items: [
      { id: "editorial", label: "消息流", icon: EnvelopeSimple },
      { id: "agents", label: "Agent 管理", icon: UsersThree },
      { id: "meetings", label: "会议中心", icon: ChatCircleDots },
    ],
  },
  {
    id: "creation",
    label: "创作",
    items: [
      { id: "works", label: "作品库", icon: BookOpen },
      { id: "chapters", label: "章节管理", icon: ListDashes },
      { id: "reader", label: "阅读数据", icon: ChartLineUp },
    ],
  },
  {
    id: "ops",
    label: "运营",
    items: [
      { id: "cost", label: "成本中心", icon: Coins },
      { id: "executions", label: "执行记录", icon: ClockCounterClockwise },
      { id: "flow", label: "链路", icon: FlowArrow },
    ],
  },
  {
    id: "system",
    label: "系统",
    items: [
      { id: "settings", label: "系统设置", icon: GearSix },
      { id: "audit", label: "留痕档案", icon: Scroll },
    ],
  },
];

export const ALL_PAGES = NAV_GROUPS.flatMap((group) => group.items);

export const PAGE_META = {
  dashboard: ["仪表盘", "编辑部现在的状态，和需要您留意的事"],
  editorial: ["消息流", "编辑之间的协作消息与今日任务"],
  agents: ["Agent 管理", "人格档案、模型参数与写作模式"],
  meetings: ["会议中心", "发起专题会议、围观讨论、查看纪要"],
  works: ["作品库", "每个项目的完整设定：大纲、角色与世界规则"],
  chapters: ["章节管理", "全部章节的写作状态、质量分与发布进度"],
  reader: ["阅读数据", "读者表现与反馈"],
  cost: ["成本中心", "API 花费与预算控制"],
  executions: ["执行记录", "每次运行的完整留痕与失败详情"],
  flow: ["链路", "调度全链路拓扑，不运行也能人工审查"],
  settings: ["系统设置", "运行、预算、模型与风格"],
  audit: ["留痕档案", "编辑部全量事件审计"],
};
