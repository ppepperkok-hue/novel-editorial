import json
import os
import tempfile
import unittest

from novel_pipeline import db
from tools import flow_graph


class FlowGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)

    def tearDown(self):
        self.conn.close()

    def test_topology_is_dag_and_connected(self):
        nodes = {n["id"] for n in flow_graph.FLOW_NODES}
        edges = flow_graph.FLOW_EDGES
        self.assertGreater(len(nodes), 30)
        self.assertGreater(len(edges), 30)
        indeg = {n: 0 for n in nodes}
        for e in edges:
            self.assertIn(e["source"], nodes)
            self.assertIn(e["target"], nodes)
            indeg[e["target"]] += 1
        queue = [n for n, d in indeg.items() if d == 0]
        seen = set(queue)
        while queue:
            cur = queue.pop()
            for e in edges:
                if e["source"] == cur and e["target"] not in seen:
                    seen.add(e["target"])
                    queue.append(e["target"])
        self.assertEqual(seen, nodes, "flow graph must be acyclic and reachable")

    def test_failed_alias_covers_scheduler_names(self):
        names = [
            "写手A", "写手B", "润色A", "润色B", "审稿A", "审稿B",
            "读者审稿A", "读者审稿B", "主编终审A", "主编终审B",
            "提炼剧情A", "提炼剧情B", "发布A", "发布B",
            "Planner出大纲", "生成作品资料", "守护细纲", "读本地资料",
            "备份数据库", "发布存稿", "记录作品资料", "全员写日记",
        ]
        for name in names:
            self.assertIn(name, flow_graph.FAILED_ALIAS, name)

    def test_build_flow_without_runs(self):
        flow = flow_graph.build_flow(self.conn)
        self.assertIsNone(flow["last_run"])
        self.assertEqual(flow["failed_ids"], [])
        self.assertEqual(len(flow["nodes"]), len(flow_graph.FLOW_NODES))

    def test_build_flow_highlights_failed_nodes(self):
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,started_at,"
            "finished_at,failed_nodes,error,published,detail,created_at) "
            "VALUES('r1',1,'manual','scheduler','failed','2026-08-11 10:00:00',"
            "'2026-08-11 10:01:00','[\"写手A\",\"发布B\"]','err',0,'{}',"
            "'2026-08-11 10:00:00')"
        )
        self.conn.commit()
        flow = flow_graph.build_flow(self.conn)
        self.assertEqual(flow["last_run"]["status"], "failed")
        self.assertEqual(set(flow["failed_ids"]), {"writer_a", "publish_b"})


if __name__ == "__main__":
    unittest.main()
