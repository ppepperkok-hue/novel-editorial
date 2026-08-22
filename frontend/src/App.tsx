import PlaceholderPanel from "./components/PlaceholderPanel";

const PANEL_TITLES = ["事件流", "穿透查询", "拍板提醒"] as const;

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Novel Editorial 面板</h1>
      </header>
      <main className="panel-windows" data-testid="panel-windows">
        {PANEL_TITLES.map((title) => (
          <PlaceholderPanel key={title} title={title} />
        ))}
      </main>
      <footer className="status-line" data-testid="status-line">
        状态：等待数据接入
      </footer>
    </div>
  );
}
