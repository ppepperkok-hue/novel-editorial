import json
import sys


def main():
    path = "outputs/novel-pipeline/n8n/novel_workflow.json"
    with open(path, encoding="utf-8") as f:
        wf = json.load(f)

    nodes = {n["name"]: n for n in wf["nodes"]}
    errors = []
    for name, node in nodes.items():
        for field in ("type", "typeVersion", "position"):
            if field not in node:
                errors.append(f"节点 {name} 缺字段 {field}")
    for src, outputs in wf.get("connections", {}).items():
        if src not in nodes:
            errors.append(f"连接起点不存在：{src}")
        for group in outputs.get("main", []):
            for link in group:
                if link["node"] not in nodes:
                    errors.append(f"连接终点不存在：{link['node']}（来自 {src}）")
    for name, node in nodes.items():
        if name not in wf.get("connections", {}) and node["type"] != "n8n-nodes-base.noOp":
            errors.append(f"节点无输出连接（可能是终点，可忽略）：{name}")

    if errors:
        print("发现问题：")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print(f"结构校验通过：{len(nodes)} 个节点，连接完整。")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    main()
