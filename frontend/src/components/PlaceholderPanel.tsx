const STATES = ["loading", "empty", "error"] as const;

type PanelState = (typeof STATES)[number];

const STATE_LABELS: Record<PanelState, string> = {
  loading: "加载中",
  empty: "暂无数据",
  error: "加载失败",
};

interface PlaceholderPanelProps {
  title: string;
}

export default function PlaceholderPanel({ title }: PlaceholderPanelProps) {
  return (
    <section className="panel" data-testid="panel-window">
      <h2 className="panel-title">{title}</h2>
      {STATES.map((state) => (
        <div
          key={state}
          className={`panel-state panel-state--${state}`}
          data-testid={`panel-state-${state}`}
        >
          {STATE_LABELS[state]}
        </div>
      ))}
    </section>
  );
}
