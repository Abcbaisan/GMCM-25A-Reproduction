"""问题二补充实验：确定性的拓扑序搜索，并独立验证每个分配结果。

这是本地补充启发式，不是论文提供的算法。先保持问题一序列作为基线，
再比较 DFS、释放节点优先和共享输入的输出节点蛇形遍历。
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'q1_reproduction'))
from q1 import Graph
from q2 import DEFAULT_ZIP, DEFAULT_Q1, SpillAllocator, save_result
from verify_q2 import verify_case


class RankedGraph(Graph):
    def dfs_rank(self, strategy):
        if strategy == 'custom':
            return self.custom_rank
        return super().dfs_rank(strategy)

    def rooted_order(self, roots):
        done, order = set(), []
        for root in roots + sorted(self.nodes):
            stack = [(root, False)]
            while stack:
                node, end = stack.pop()
                if node in done:
                    continue
                if end:
                    done.add(node)
                    order.append(node)
                else:
                    stack.append((node, True))
                    stack.extend((p, False) for p in sorted(self.pred[node], reverse=True) if p not in done)
        self.custom_rank = {node: i for i, node in enumerate(order)}
        return self.compact(self.initial('dfs_custom'))


def footprint(graph, root):
    """输出节点祖先中 COPY_IN 使用的缓冲区集合。"""
    seen, copied, stack = set(), set(), [root]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        if graph.nodes[node]['Op'] == 'COPY_IN':
            copied.update(graph.nodes[node]['Bufs'])
        stack.extend(graph.pred[node])
    return copied


def families(graph):
    roots = sorted(v for v, n in graph.nodes.items() if n['Op'] == 'COPY_OUT')
    incidence = {}
    for root in roots:
        for buf in footprint(graph, root):
            incidence.setdefault(buf, set()).add(root)
    groups = sorted({tuple(sorted(v)) for v in incidence.values()}, key=lambda x: (-len(x), x))
    remaining, result = set(roots), []
    for group in groups:
        if set(group) <= remaining:
            result.append(list(group))
            remaining.difference_update(group)
    return result + [[r] for r in sorted(remaining)]


def snake(groups, width, short_first, lane_mode):
    """交错访问共享输入的输出组，相邻块反转访问方向以尝试延长复用。"""
    chunks, start = [], 0
    first = len(groups) % width if short_first and len(groups) % width else width
    while start < len(groups):
        size = first if not chunks else width
        chunks.append(groups[start:start + size])
        start += size
    result = []
    for ci, chunk in enumerate(chunks):
        indices = list(range(max(map(len, chunk))))
        if ci % 2:
            indices.reverse()
        for k, j in enumerate(indices):
            reverse = lane_mode == 'reverse' or (lane_mode == 'alternate' and k % 2)
            for group in (chunk[::-1] if reverse else chunk):
                if j < len(group):
                    result.append(group[j])
    return result


def candidates(graph, original):
    yield 'q1-final', lambda: original
    for strategy in ['dfs_id_asc', 'dfs_id_desc', 'dfs_size_asc', 'dfs_size_desc']:
        yield strategy, lambda s=strategy: graph.compact(graph.initial(s))
    free = [v for v, n in graph.nodes.items() if n['Op'] == 'FREE']
    for typ in ['L0C', 'UB', 'L1', 'L0A', 'L0B']:
        selected = [v for v in free if graph.nodes[v]['Type'] == typ]
        for reverse in [False, True]:
            roots = sorted(selected, reverse=reverse) + sorted(set(free) - set(selected), reverse=reverse)
            yield f'free-{typ}-reverse-{reverse}', lambda r=roots: graph.rooted_order(r)
    groups = families(graph)
    for width in [2, 3, 4]:
        for short in [False, True]:
            for lanes in ['normal', 'reverse', 'alternate']:
                label = f'snake-width-{width}-short-{short}-lanes-{lanes}'
                yield label, lambda w=width, s=short, l=lanes: graph.rooted_order(snake(groups, w, s, l))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', default=DEFAULT_ZIP)
    parser.add_argument('--schedule-dir', type=Path, default=DEFAULT_Q1)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    # 显式新目录，避免覆盖历史实验。
    args.out.mkdir(parents=True, exist_ok=False)
    input_dir = args.out / 'input_schedules'
    input_dir.mkdir()
    report = {}
    with zipfile.ZipFile(args.zip) as archive:
        for name in sorted(n for n in archive.namelist() if n.endswith('.json')):
            case = Path(name).stem
            data = json.loads(archive.read(name))
            graph = RankedGraph(data, True, 'l1ub', True)
            original = list(map(int, (args.schedule_dir / f'{case}_schedule.txt').read_text().split()))
            best, best_order, best_label, rows = None, None, None, []
            seen = set()
            for label, make_order in candidates(graph, original):
                try:
                    order = make_order()
                    key = tuple(order)
                    if key in seen:
                        rows.append({'strategy': label, 'duplicate_schedule': True})
                        continue
                    seen.add(key)
                    graph.validate(order)
                    result = SpillAllocator(data, order, 'farthest', 'best-fit').run()
                    check = verify_case(data, result['schedule'], result['memory'], result['spills'])
                    if check['extra_data_movement'] != result['additional_transfer']:
                        raise ValueError('搬运量与独立验证不一致')
                    rows.append({'strategy': label, 'transfer': result['additional_transfer'], 'spills': result['spill_count'], 'valid': True})
                    if best is None or (result['additional_transfer'], result['spill_count']) < (best['additional_transfer'], best['spill_count']):
                        best, best_order, best_label = result, order, label
                        print(case, label, result['additional_transfer'], result['spill_count'], flush=True)
                except ValueError as error:
                    rows.append({'strategy': label, 'valid': False, 'error': str(error)})
            if best is None:
                raise ValueError(f'{case}: 无有效结果')
            save_result(args.out, case, best)
            (input_dir / f'{case}_schedule.txt').write_text('\n'.join(map(str, best_order)) + '\n', encoding='utf-8')
            report[case] = {'strategy': best_label, 'additional_transfer': best['additional_transfer'], 'spill_count': best['spill_count'], 'trials': rows}
            (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
