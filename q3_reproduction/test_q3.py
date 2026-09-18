"""问题三的独立小算例回归；运行 python -m unittest discover。"""
import unittest

from q3 import PipelineModel, critical_order, improve_swaps
from verify_q2 import verify_case


def toy_case():
    # B 的 MTE2 先发射会延迟 A 的长 CUBE 关键路径。
    data = {"Nodes": [
        {"Id": 0, "Op": "ALLOC", "BufId": 10, "Type": "UB", "Size": 100},
        {"Id": 1, "Op": "ALLOC", "BufId": 20, "Type": "UB", "Size": 100},
        {"Id": 2, "Op": "COPY_IN", "Pipe": "MTE2", "Cycles": 10, "Bufs": [20]},
        {"Id": 3, "Op": "COPY_IN", "Pipe": "MTE2", "Cycles": 10, "Bufs": [10]},
        {"Id": 4, "Op": "MATMUL", "Pipe": "CUBE", "Cycles": 100, "Bufs": [10]},
        {"Id": 5, "Op": "MATMUL", "Pipe": "CUBE", "Cycles": 1, "Bufs": [20]},
        {"Id": 6, "Op": "FREE", "BufId": 10, "Type": "UB", "Size": 100},
        {"Id": 7, "Op": "FREE", "BufId": 20, "Type": "UB", "Size": 100},
    ], "Edges": [[0, 3], [1, 2], [3, 4], [2, 5], [4, 6], [5, 7]]}
    baseline = [0, 1, 2, 3, 4, 5, 6, 7]
    return data, baseline, {10: 0, 20: 100}, []


class Q3Tests(unittest.TestCase):
    def test_pipeline_and_adjacent_swap(self):
        data, schedule, memory, spills = toy_case()
        self.assertTrue(verify_case(data, schedule, memory, spills)["validated"])
        model = PipelineModel(data, schedule, memory, spills)
        self.assertEqual(model.makespan(schedule), 121)
        better, time, statistics = improve_swaps(model, schedule, budget=30, passes=2)
        self.assertEqual(time, 111)
        self.assertEqual(better, [0, 1, 3, 2, 4, 5, 6, 7])
        self.assertTrue(verify_case(data, better, memory, spills)["validated"])
        self.assertGreater(statistics["accepted_swaps"], 0)

    def test_reuse_edges(self):
        data = {"Nodes": [
            {"Id": 0, "Op": "ALLOC", "BufId": 10, "Type": "UB", "Size": 100},
            {"Id": 1, "Op": "COPY_IN", "Pipe": "MTE2", "Cycles": 10, "Bufs": [10]},
            {"Id": 2, "Op": "FREE", "BufId": 10, "Type": "UB", "Size": 100},
            {"Id": 3, "Op": "ALLOC", "BufId": 20, "Type": "UB", "Size": 100},
            {"Id": 4, "Op": "COPY_IN", "Pipe": "MTE2", "Cycles": 20, "Bufs": [20]},
            {"Id": 5, "Op": "FREE", "BufId": 20, "Type": "UB", "Size": 100},
        ], "Edges": [[0, 1], [1, 2], [3, 4], [4, 5]]}
        schedule, memory = list(range(6)), {10: 0, 20: 0}
        self.assertTrue(verify_case(data, schedule, memory, [])["validated"])
        model = PipelineModel(data, schedule, memory, [])
        self.assertIn(2, model.preds[3])
        self.assertEqual(model.makespan(schedule), 30)

    def test_critical_topology(self):
        data, _, _, _ = toy_case()
        order = critical_order(data)
        positions = {v: i for i, v in enumerate(order)}
        self.assertEqual(set(order), set(range(8)))
        self.assertTrue(all(positions[u] < positions[v] for u, v in data["Edges"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
