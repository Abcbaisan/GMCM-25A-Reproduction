"""问题三：基于独立流水估时、合法性复核和受限候选搜索优化问题二结果。

使用官方原图及问题二正式三文件；仅选择通过 verify_q2 的方案。
所有官方实验结果须由实际运行生成，不预填数值。
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import heapq
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
Q2 = ROOT / "q2_reproduction"
sys.path.insert(0, str(Q2))
from q2 import CAPACITIES, SpillAllocator  # noqa: E402
from verify_q2 import read_result_files, verify_case  # noqa: E402

DEFAULT_ZIP = ROOT / "通用神经网络处理器下的核内调度问题附件.zip"
DEFAULT_BASELINE = Q2 / "runs" / "q2-20260914" / "optimized"
DEFAULT_ALTERNATIVE = Q2 / "results"
DEFAULT_OUT = ROOT / "q3_reproduction" / "results"


class PipelineModel:
    """原图/SPILL/地址复用依赖加上各 Pipe FIFO 的最早完成时间模型。"""

    def __init__(self, data, schedule, memory, spills):
        self.nodes = {node["Id"]: node for node in data["Nodes"]}
        self.n = len(self.nodes)
        self.spills = list(spills)
        total = self.n + 2 * len(spills)
        self.preds = [set() for _ in range(total)]
        self.pipe = [None] * total
        self.cycles = [0] * total
        self.orig_edges = set(map(tuple, data["Edges"]))
        self.position = {v: i for i, v in enumerate(schedule)}
        self.alloc = {node["BufId"]: node for node in data["Nodes"] if node["Op"] == "ALLOC"}
        self.free = {node["BufId"]: node for node in data["Nodes"] if node["Op"] == "FREE"}
        copied = {b for node in data["Nodes"] if node["Op"] == "COPY_IN" for b in node["Bufs"]}
        uses = defaultdict(list)
        for node in data["Nodes"]:
            v = node["Id"]
            if node["Op"] not in ("ALLOC", "FREE"):
                self.pipe[v] = node["Pipe"]
                self.cycles[v] = int(node["Cycles"])
                if self.cycles[v] < 0:
                    raise ValueError(f"节点 {v} 的 Cycles 为负")
                for b in set(node["Bufs"]):
                    uses[b].append(v)

        def edge(u, v):
            if self.position[u] >= self.position[v]:
                raise ValueError(f"依赖反向：{u}->{v}")
            self.preds[v].add(u)

        for u, v in self.orig_edges:
            edge(u, v)

        previous_in = {}
        for k, (b, _) in enumerate(spills):
            out_id, in_id = self.n + 2 * k, self.n + 2 * k + 1
            size = self.alloc[b]["Size"]
            self.pipe[out_id], self.pipe[in_id] = "MTE3", "MTE2"
            self.cycles[out_id] = 0 if b in copied else 2 * size + 150
            self.cycles[in_id] = 2 * size + 150
            edge(self.alloc[b]["Id"], out_id)
            edge(out_id, in_id)
            edge(in_id, self.free[b]["Id"])
            if b in previous_in:
                edge(previous_in[b], out_id)
            previous_in[b] = in_id
            for v in uses[b]:
                if self.position[v] < self.position[out_id]:
                    edge(v, out_id)
                elif self.position[v] > self.position[in_id]:
                    edge(in_id, v)
                else:
                    raise ValueError(f"Buf{b} 在 OUT/IN 中间被使用")

        # 按地址单元独立重放物理占用，对复用建立 上次释放 -> 本次申请 的边。
        owners = {t: [None] * cap for t, cap in CAPACITIES.items()}
        last_release = {t: [None] * cap for t, cap in CAPACITIES.items()}
        resident = {}
        self.reuse_edges = 0

        def acquire(b, off, v):
            t, size = self.alloc[b]["Type"], self.alloc[b]["Size"]
            if not (0 <= off and off + size <= CAPACITIES[t]) or b in resident:
                raise ValueError(f"非法的地址申请: node={v}, buf={b}")
            if any(owner is not None for owner in owners[t][off:off + size]):
                raise ValueError(f"地址重叠: node={v}, buf={b}")
            for previous in set(last_release[t][off:off + size]) - {None}:
                edge(previous, v)
                self.reuse_edges += 1
            owners[t][off:off + size] = [b] * size
            resident[b] = off

        def release(b, v):
            if b not in resident:
                raise ValueError(f"释放未驻留缓冲区: node={v}, buf={b}")
            t, size = self.alloc[b]["Type"], self.alloc[b]["Size"]
            off = resident.pop(b)
            if any(owner != b for owner in owners[t][off:off + size]):
                raise ValueError(f"地址所有者错误: node={v}, buf={b}")
            owners[t][off:off + size] = [None] * size
            last_release[t][off:off + size] = [v] * size

        for v in schedule:
            if v >= self.n:
                k, direction = divmod(v - self.n, 2)
                b, new_off = spills[k]
                if direction == 0:
                    release(b, v)
                else:
                    acquire(b, new_off, v)
            else:
                node = self.nodes[v]
                if node["Op"] == "ALLOC":
                    acquire(node["BufId"], memory[node["BufId"]], v)
                elif node["Op"] == "FREE":
                    release(node["BufId"], v)
        if resident:
            raise ValueError("模拟结束后仍有驻留缓冲区")

    def makespan(self, schedule):
        """相同 Pipe 按调度序列执行，不同 Pipe 可重叠；ALLOC/FREE 零周期。"""
        finish = [-1] * len(self.preds)
        pipe_finish = defaultdict(int)
        latest = 0
        for v in schedule:
            dep_end = 0
            for u in self.preds[v]:
                if finish[u] < 0:
                    raise ValueError(f"调度不满足依赖：{u}->{v}")
                dep_end = max(dep_end, finish[u])
            pipe = self.pipe[v]
            start = max(dep_end, pipe_finish[pipe]) if pipe else dep_end
            end = start + self.cycles[v]
            finish[v] = end
            if pipe:
                pipe_finish[pipe] = end
            latest = max(latest, end)
        return latest


def critical_order(data, free_first=False):
    """可选关键路径拓扑序；地址和 SPILL 由问题二重新求解。"""
    nodes = {x["Id"]: x for x in data["Nodes"]}
    n = len(nodes)
    succ = [[] for _ in range(n)]
    indeg = [0] * n
    for u, v in data["Edges"]:
        succ[u].append(v)
        indeg[v] += 1
    ready = [v for v in range(n) if indeg[v] == 0]
    heapq.heapify(ready)
    topo = []
    while ready:
        u = heapq.heappop(ready)
        topo.append(u)
        for v in succ[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                heapq.heappush(ready, v)
    if len(topo) != n:
        raise ValueError("原始图不是 DAG")
    rank = [0] * n
    for v in reversed(topo):
        duration = 0 if nodes[v]["Op"] in ("ALLOC", "FREE") else int(nodes[v]["Cycles"])
        rank[v] = duration + max((rank[u] for u in succ[v]), default=0)
    indeg = [0] * n
    for u, v in data["Edges"]:
        indeg[v] += 1
    heap = []

    def priority(v):
        node = nodes[v]
        if free_first:
            return (0 if node["Op"] == "FREE" else 1, -rank[v], v)
        return (-rank[v], 0 if node["Op"] == "FREE" else 1, v)

    for v in range(n):
        if indeg[v] == 0:
            heapq.heappush(heap, priority(v))
    order = []
    while heap:
        *_, v = heapq.heappop(heap)
        order.append(v)
        for u in succ[v]:
            indeg[u] -= 1
            if indeg[u] == 0:
                heapq.heappush(heap, priority(u))
    return order


def improve_swaps(model, schedule, budget=64, passes=2):
    """只交换相邻的、同 Pipe 且缓冲区不相交的独立普通节点。"""
    result = list(schedule)
    best_time = model.makespan(result)
    accepted = 0
    tested = 0
    for _ in range(passes):
        candidates = []
        for i in range(len(result) - 1):
            a, b = result[i:i + 2]
            if a >= model.n or b >= model.n:
                continue
            na, nb = model.nodes[a], model.nodes[b]
            if na["Op"] in ("ALLOC", "FREE") or nb["Op"] in ("ALLOC", "FREE"):
                continue
            if model.pipe[a] != model.pipe[b] or not model.pipe[a]:
                continue
            if set(na["Bufs"]) & set(nb["Bufs"]):
                continue
            if (a, b) in model.orig_edges:
                continue
            candidates.append(i)
        if not candidates or budget <= 0:
            break
        if len(candidates) > budget:
            candidates = [candidates[j * len(candidates) // budget] for j in range(budget)]
        winner, winner_time = None, best_time
        for i in candidates:
            result[i], result[i + 1] = result[i + 1], result[i]
            try:
                score = model.makespan(result)
            finally:
                result[i], result[i + 1] = result[i + 1], result[i]
            tested += 1
            if score < winner_time:
                winner, winner_time = i, score
        if winner is None:
            break
        result[winner], result[winner + 1] = result[winner + 1], result[winner]
        best_time = winner_time
        accepted += 1
    return result, best_time, {"evaluated_swaps": tested, "accepted_swaps": accepted}


def save_three(out, case, schedule, memory, spills):
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{case}_schedule.txt").write_text("".join(f"{v}\n" for v in schedule), encoding="utf-8")
    (out / f"{case}_memory.txt").write_text("".join(f"{b}:{off}\n" for b, off in sorted(memory.items())), encoding="utf-8")
    (out / f"{case}_spill.txt").write_text("".join(f"{b}:{off}\n" for b, off in spills), encoding="utf-8")


def solve_one(data, case, baseline_dir, alternative_dir, out, tolerance, max_swaps, passes):
    baseline = read_result_files(baseline_dir, case)
    baseline_check = verify_case(data, *baseline)
    baseline_model = PipelineModel(data, *baseline)
    base_time = baseline_model.makespan(baseline[0])
    limit = baseline_check["extra_data_movement"] * (1 + tolerance / 100)
    best = (baseline, base_time, "q2-optimized-baseline", baseline_check)
    rows = [{"candidate": best[2], "cycles": base_time, "extra_data": baseline_check["extra_data_movement"], "valid": True, "accepted": True}]

    def consider(label, solution):
        nonlocal best
        try:
            check = verify_case(data, *solution)
            movement = check["extra_data_movement"]
            if movement > limit + 1e-8:
                rows.append({"candidate": label, "valid": True, "accepted": False, "extra_data": movement, "reason": "超过搬运量上限"})
                return
            model = PipelineModel(data, *solution)
            time = model.makespan(solution[0])
            improved = (time, movement, len(solution[2])) < (best[1], best[3]["extra_data_movement"], len(best[0][2]))
            if improved:
                best = (solution, time, label, check)
            rows.append({"candidate": label, "valid": True, "accepted": improved, "cycles": time, "extra_data": movement, "spills": len(solution[2])})
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            rows.append({"candidate": label, "valid": False, "error": str(exc)})

    if alternative_dir and (alternative_dir / f"{case}_schedule.txt").exists():
        consider("q2-results", read_result_files(alternative_dir, case))

    original = [v for v in baseline[0] if v < len(data["Nodes"])]
    schedules = [("q2-original-order", original)]
    for free in (False, True):
        schedules.append(("critical-free" if free else "critical", critical_order(data, free)))
    seen = set()
    for label, order in schedules:
        key = tuple(order)
        if key in seen:
            continue
        seen.add(key)
        for policy in ("farthest", "cost-distance"):
            for placement in ("best-fit", "first-fit") if label == "q2-original-order" else ("best-fit",):
                try:
                    r = SpillAllocator(data, order, policy, placement).run()
                    if verify_case(data, r["schedule"], r["memory"], r["spills"])["extra_data_movement"] != r["additional_transfer"]:
                        raise ValueError("求解器和验证器搬运量不一致")
                    consider(f"{label}/{policy}/{placement}", (r["schedule"], r["memory"], r["spills"]))
                except (ValueError, KeyError, TypeError, IndexError) as exc:
                    rows.append({"candidate": f"{label}/{policy}/{placement}", "valid": False, "error": str(exc)})

    solution, _, _, _ = best
    model = PipelineModel(data, *solution)
    candidate_schedule, candidate_time, swap_stats = improve_swaps(model, solution[0], max_swaps, passes)
    if candidate_time < best[1]:
        consider("adjacent-swap-refinement", (candidate_schedule, solution[1], solution[2]))
    else:
        rows.append({"candidate": "adjacent-swap-refinement", "valid": True, "accepted": False, "cycles": candidate_time, **swap_stats})

    solution, time, label, check = best
    final_check = verify_case(data, *solution)
    if final_check["extra_data_movement"] > limit + 1e-8 or time > base_time:
        raise AssertionError("最终方案不满足问题三的基线约束")
    save_three(out, case, *solution)
    return {
        "baseline_source": str(baseline_dir),
        "baseline_cycles": base_time,
        "baseline_extra_data": baseline_check["extra_data_movement"],
        "movement_limit_percent": tolerance,
        "selected_candidate": label,
        "optimized_cycles": time,
        "optimized_extra_data": final_check["extra_data_movement"],
        "time_reduction_percent": round((base_time - time) * 100 / base_time, 5) if base_time else 0,
        "spill_pairs": len(solution[2]),
        "validated": final_check["validated"],
        "swap_search": swap_stats,
        "trials": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--alternative", type=Path, default=DEFAULT_ALTERNATIVE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--case", default="all")
    parser.add_argument("--tolerance-pct", type=float, default=5.0)
    parser.add_argument("--max-swaps", type=int, default=64)
    parser.add_argument("--swap-passes", type=int, default=2)
    args = parser.parse_args(argv)
    if args.tolerance_pct < 0 or args.max_swaps < 0 or args.swap_passes < 0:
        parser.error("容忍百分比和搜索次数不能为负")
    report = {}
    with zipfile.ZipFile(args.zip) as archive:
        names = sorted(n for n in archive.namelist() if n.endswith(".json") and (args.case == "all" or Path(n).stem == args.case))
        if not names:
            parser.error("ZIP 中没有匹配的 JSON 算例")
        for name in names:
            case = Path(name).stem
            try:
                data = json.loads(archive.read(name))
                report[case] = solve_one(data, case, args.baseline, args.alternative, args.out, args.tolerance_pct, args.max_swaps, args.swap_passes)
                r = report[case]
                print(f"{case}: valid=True, time {r['baseline_cycles']} -> {r['optimized_cycles']}, movement {r['baseline_extra_data']} -> {r['optimized_extra_data']}", flush=True)
            except (ValueError, KeyError, OSError, TypeError, IndexError, AssertionError) as exc:
                report[case] = {"validated": False, "error": str(exc)}
                print(f"{case}: valid=False, {exc}", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not all(r.get("validated") for r in report.values()):
        raise SystemExit(1)
    return report


if __name__ == "__main__":
    main()
