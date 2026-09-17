"""少量关键正确性回归：python test_q2.py；只使用 unittest 标准库。"""

import copy
import unittest

from q2 import SpillAllocator
from verify_q2 import verify_case


def two_buffers():
    """两块各 700 的 UB 缓冲区，必须避免同时物理驻留。"""
    nodes = [
        {"Id": 0, "Op": "ALLOC", "BufId": 0, "Type": "UB", "Size": 700},
        {"Id": 1, "Op": "COPY_IN", "Bufs": [0]},
        {"Id": 2, "Op": "ALLOC", "BufId": 1, "Type": "UB", "Size": 700},
        {"Id": 3, "Op": "COPY_IN", "Bufs": [1]},
        {"Id": 4, "Op": "ADD", "Bufs": [1]},
        {"Id": 5, "Op": "FREE", "BufId": 1, "Type": "UB", "Size": 700},
        {"Id": 6, "Op": "ADD", "Bufs": [0]},
        {"Id": 7, "Op": "FREE", "BufId": 0, "Type": "UB", "Size": 700},
    ]
    return {"Nodes": nodes, "Edges": [[0, 1], [1, 6], [6, 7], [2, 3], [3, 4], [4, 5]]}


def fragmentation_example():
    """实际地址能比理想空闲布局更碎：需有代价地重新打包，才能完成。"""
    nodes = []

    def management(op, buf, size):
        nodes.append({"Id": len(nodes), "Op": op, "BufId": buf, "Type": "UB", "Size": size})

    def operation(op, bufs):
        nodes.append({"Id": len(nodes), "Op": op, "Bufs": bufs})

    # A500、B350 被 X600 挤出；X 释放后，U200 占据 [0,200)。
    # ADD 需要重新载入 A 和 B：先放 A 会占 [200,700)，
    # 即使随后换出 U，剩下 [0,200)、[700,1024) 也无法放入 B350。
    # 求解器必须允许已恢复的 A 再次真实 OUT/IN，重新紧凑布局。
    management("ALLOC", 0, 500)
    operation("COPY_IN", [0])
    management("ALLOC", 1, 350)
    operation("COPY_IN", [1])
    management("ALLOC", 2, 600)
    operation("COPY_IN", [2])
    management("FREE", 2, 600)
    management("ALLOC", 3, 200)
    operation("COPY_IN", [3])
    operation("ADD", [0, 1])
    management("FREE", 0, 500)
    management("FREE", 1, 350)
    management("FREE", 3, 200)
    edges = [[0, 1], [1, 9], [9, 10], [2, 3], [3, 9], [9, 11],
             [4, 5], [5, 6], [7, 8], [8, 12]]
    return {"Nodes": nodes, "Edges": edges}


class Q2CriticalTests(unittest.TestCase):
    def setUp(self):
        self.data = two_buffers()
        self.schedule = [0, 1, 8, 2, 3, 4, 5, 9, 6, 7]
        self.memory = {0: 0, 1: 0}

    def test_copy_in_cost_and_reuse_barriers(self):
        result = verify_case(self.data, self.schedule, self.memory, [(0, 0)])
        self.assertEqual(result["extra_data_movement"], 700)
        self.assertEqual(result["peak_resident_by_type"]["UB"], 700)
        self.assertEqual(result["reuse_barrier_count"], 2)
        generated = copy.deepcopy(self.data)
        generated["Nodes"][1]["Op"] = "GENERATE"
        result = verify_case(generated, self.schedule, self.memory, [(0, 0)])
        self.assertEqual(result["extra_data_movement"], 1400)

    def test_repeated_spills_and_crossing_rejection(self):
        valid = [0, 1, 8, 9, 10, 2, 3, 4, 5, 11, 6, 7]
        result = verify_case(self.data, valid, self.memory, [(0, 0), (0, 0)])
        self.assertEqual(result["spill_pairs"], 2)
        self.assertEqual(result["extra_data_movement"], 1400)
        crossed = [0, 1, 8, 10, 2, 3, 4, 5, 9, 11, 6, 7]
        with self.assertRaises(ValueError):
            verify_case(self.data, crossed, self.memory, [(0, 0), (0, 0)])

    def test_capacity_and_overlap_rejection(self):
        with self.subTest("resident overlap"), self.assertRaises(ValueError):
            verify_case(self.data, list(range(8)), self.memory, [])
        with self.subTest("initial allocation out of bounds"), self.assertRaises(ValueError):
            verify_case(self.data, self.schedule, {0: 400, 1: 0}, [(0, 0)])
        with self.subTest("reload out of bounds"), self.assertRaises(ValueError):
            verify_case(self.data, self.schedule, self.memory, [(0, 400)])

    def test_nonresident_use_and_free_rejection(self):
        before_reload = [0, 1, 8, 2, 3, 4, 5, 6, 9, 7]
        with self.subTest("operation before reload"), self.assertRaises(ValueError):
            verify_case(self.data, before_reload, self.memory, [(0, 0)])
        before_reload = [0, 1, 8, 2, 3, 4, 5, 6, 7, 9]
        with self.subTest("FREE before reload"), self.assertRaises(ValueError):
            verify_case(self.data, before_reload, self.memory, [(0, 0)])

    def test_original_dependency_and_spill_row_order(self):
        reversed_edge = [1, 0, 8, 2, 3, 4, 5, 9, 6, 7]
        with self.subTest("original edge"), self.assertRaises(ValueError):
            verify_case(self.data, reversed_edge, self.memory, [(0, 0)])
        reversed_rows = [0, 1, 10, 11, 8, 2, 3, 4, 5, 9, 6, 7]
        with self.subTest("SPILL row order"), self.assertRaises(ValueError):
            verify_case(self.data, reversed_rows, self.memory, [(0, 0), (0, 0)])

    def test_fragmentation_repack_is_real_and_paid(self):
        data = fragmentation_example()
        order = list(range(len(data["Nodes"])))
        for policy in ("paper-small", "paper-large", "farthest", "cost-distance"):
            for placement in ("best-fit", "first-fit"):
                with self.subTest(policy=policy, placement=placement):
                    result = SpillAllocator(data, order, policy, placement).run()
                    validated = verify_case(data, result["schedule"], result["memory"], result["spills"])
                    self.assertGreaterEqual(result["repack_count"], 1)
                    self.assertEqual(result["additional_transfer"], validated["extra_data_movement"])
                    self.assertEqual(result["spill_count"], validated["spill_pairs"])
                    # 初次 A/B 换出成本 850 以外，重新打包必须产生真实额外代价。
                    self.assertGreater(result["additional_transfer"], 850)
                    self.assertEqual([v for v in result["schedule"] if v < len(order)], order)


if __name__ == "__main__":
    unittest.main(verbosity=2)
