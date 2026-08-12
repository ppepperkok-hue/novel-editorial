import { useEffect } from "react";

/** @internal 新壳占位：阶段 4 将替换为五区导航 + HashRouter。 */
export default function App() {
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  }, []);
  return (
    <div
      style={{
        height: "100vh",
        display: "grid",
        placeItems: "center",
        fontFamily: "system-ui, sans-serif",
        color: "#9a958c",
      }}
    >
      编辑部面板重建中…
    </div>
  );
}
