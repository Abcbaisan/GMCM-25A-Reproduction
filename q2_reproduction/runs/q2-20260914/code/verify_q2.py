"""问题二独立结果验证器：只依赖标准库，不导入求解器。

按题面附录 B、C、E 读取和重放调度、初始地址以及 SPILL 清单。
数组模拟真实连续地址；它与求解器的空闲块管理实现相互独立。
验证范围是调度顺序、依赖、缓存生命周期、物理容量和额外搬运量，
不计算问题三涉及的多流水执行时间。
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import zipfile


CAPACITIES = {"L1": 4096, "UB": 1024, "L0A": 256, "L0B": 256, "L0C": 512}
DEFAULT_ZIP = r"D:/BaiduNetdiskDownload/华为杯/真题/2025年年中国研究生数学建模竞赛赛题/A题/通用神经网络处理器下的核内调度问题附件.zip"


def _require(condition, message):
    """不用 assert，使 python -O 运行时也不会关闭结果验证。"""
    if not condition:
        raise ValueError(message)


def _integer(value, description):
    _require(type(value) is int, f"{description}必须是整数，实际为 {value!r}")
    return value


def verify_case(data, schedule, memory, spills):
    """独立验证一个算例；成功返回指标字典，失败抛出 ValueError。

    data: 官方 JSON 解析后的字典。
    schedule: 包含原节点及新增节点的整数 Id 列表。
    memory: {BufId: 初始 ALLOC 地址偏移}，每个缓冲区恰好一项。
    spills: [(BufId, SPILL_IN 新偏移), ...]，按 SPILL_OUT 发生顺序。
            第 k 项 (k 从 0 开始) 对应 N+2*k、N+2*k+1 两个节点。
    """
    _require(isinstance(data, dict), "输入数据必须是字典")
    _require(isinstance(data.get("Nodes"), list), "Nodes 必须是列表")
    _require(isinstance(data.get("Edges"), list), "Edges 必须是列表")
    nodes = {}
    alloc = {}
    free = {}
    users = {}
    copy_in_buffers = set()

    for node in data["Nodes"]:
        _require(isinstance(node, dict), "节点必须是字典")
        node_id = _integer(node.get("Id"), "节点 Id")
        _require(node_id not in nodes, f"原图节点 Id 重复：{node_id}")
        _require(isinstance(node.get("Op"), str), f"节点 {node_id} 缺少 Op")
        _require(node["Op"] not in ("SPILL_OUT", "SPILL_IN"),
                 f"原始 JSON 不应包含 SPILL 节点 {node_id}")
        nodes[node_id] = node
        if node["Op"] in ("ALLOC", "FREE"):
            buf = _integer(node.get("BufId"), f"节点 {node_id} BufId")
            _require(buf >= 0, f"节点 {node_id} 的 BufId 为负")
            size = _integer(node.get("Size"), f"Buf{buf} Size")
            _require(size > 0, f"Buf{buf} Size 必须为正")
            _require(node.get("Type") in CAPACITIES,
                     f"Buf{buf} 不支持的缓存类型：{node.get('Type')!r}")
            target = alloc if node["Op"] == "ALLOC" else free
            _require(buf not in target, f"Buf{buf} 有重复 {node['Op']}")
            target[buf] = node
        else:
            _require(isinstance(node.get("Bufs"), list),
                     f"操作节点 {node_id} 缺少 Bufs 列表")
            for buf in node["Bufs"]:
                _integer(buf, f"操作节点 {node_id} Bufs 中的 BufId")
            for buf in set(node["Bufs"]):
                users.setdefault(buf, set()).add(node_id)
            if node["Op"] == "COPY_IN":
                copy_in_buffers.update(node["Bufs"])

    n = len(nodes)
    _require(set(nodes) == set(range(n)), f"原节点 Id 必须恰好为 0 到 {n - 1}")
    _require(set(alloc) == set(free), "ALLOC 与 FREE 的 BufId 集合不一致")
    for buf, node in alloc.items():
        _require((node["Type"], node["Size"]) == (free[buf]["Type"], free[buf]["Size"]),
                 f"Buf{buf} ALLOC/FREE 的 Type 或 Size 不一致")
        _require(node["Size"] <= CAPACITIES[node["Type"]],
                 f"Buf{buf} 本身大小 {node['Size']} 超出 {node['Type']} 容量")
    _require(set(users) <= set(alloc), f"操作引用未声明的缓冲区：{sorted(set(users) - set(alloc))[:10]}")

    _require(isinstance(memory, dict), "memory 必须是字典")
    for buf, offset in memory.items():
        _integer(buf, "memory BufId")
        _integer(offset, f"Buf{buf} 初始 Offset")
    _require(set(memory) == set(alloc),
             f"memory 缓冲区不完整或含多余条目：缺失 {sorted(set(alloc) - set(memory))[:10]}，"
             f"多余 {sorted(set(memory) - set(alloc))[:10]}")

    _require(isinstance(spills, (list, tuple)), "spills 必须是列表或元组")
    for k, item in enumerate(spills):
        _require(isinstance(item, (list, tuple)) and len(item) == 2,
                 f"SPILL 第 {k + 1} 项必须为 (BufId, NewOffset)")
        buf, offset = item
        _integer(buf, f"SPILL 第 {k + 1} 项 BufId")
        _integer(offset, f"SPILL 第 {k + 1} 项 NewOffset")
        _require(buf in alloc, f"SPILL 第 {k + 1} 项引用未知 Buf{buf}")

    schedule = list(schedule)
    for node_id in schedule:
        _integer(node_id, "schedule 节点 Id")
    required_ids = set(range(n + 2 * len(spills)))
    _require(len(schedule) == len(required_ids),
             f"调度长度错误：应有 {len(required_ids)} 个节点，实际 {len(schedule)}")
    _require(len(set(schedule)) == len(schedule), "调度中存在重复节点")
    _require(set(schedule) == required_ids,
             f"调度节点集合错误：缺失 {sorted(required_ids - set(schedule))[:10]}，"
             f"多余 {sorted(set(schedule) - required_ids)[:10]}")
    positions = {node_id: i for i, node_id in enumerate(schedule)}
    for edge in data["Edges"]:
        _require(isinstance(edge, (list, tuple)) and len(edge) == 2,
                 f"非法依赖边：{edge!r}")
        u, v = edge
        _integer(u, "依赖边起点")
        _integer(v, "依赖边终点")
        _require(u in nodes and v in nodes, f"依赖边 {u}→{v} 引用未知节点")
        _require(positions[u] < positions[v], f"原图依赖不满足：{u}→{v}")
    for buf in alloc:
        _require(positions[alloc[buf]["Id"]] < positions[free[buf]["Id"]],
                 f"Buf{buf} 的 FREE 先于 ALLOC")

    # 显式核查附录 B 的新增边。按每个 buffer 的全部操作时间线处理，
    # 其中包括其他 SPILL 节点；自己的一对 OUT/IN 不产生自环。
    operations = {buf: [] for buf in alloc}
    for node_id in schedule:
        if node_id < n:
            node = nodes[node_id]
            if node["Op"] not in ("ALLOC", "FREE"):
                for buf in set(node["Bufs"]):
                    operations[buf].append(node_id)
        else:
            buf = spills[(node_id - n) // 2][0]
            operations[buf].append(node_id)
    operation_indices = {
        buf: {node_id: index for index, node_id in enumerate(stream)}
        for buf, stream in operations.items()
    }
    last_out_position = -1
    spill_dependency_checks = 0
    for k, (buf, _) in enumerate(spills):
        out_id, in_id = n + 2 * k, n + 2 * k + 1
        out_pos, in_pos = positions[out_id], positions[in_id]
        _require(last_out_position < out_pos,
                 f"SPILL 第 {k + 1} 行与 SPILL_OUT 实际发生顺序不一致")
        last_out_position = out_pos
        _require(positions[alloc[buf]["Id"]] < out_pos < in_pos < positions[free[buf]["Id"]],
                 f"SPILL 第 {k + 1} 对未满足 ALLOC→OUT→IN→FREE")
        stream = operations[buf]
        index = operation_indices[buf][out_id]
        _require(index + 1 < len(stream) and stream[index + 1] == in_id,
                 f"Buf{buf} 的 OUT {out_id} 与 IN {in_id} 之间存在缓冲区使用或交叉 SPILL")
        # OUT 之前的所有使用已经位于它之前；IN 是下一次使用事件，
        # 所以所有其他未来使用必定位于 IN 之后。用相邻事件验证避免 O(KN) 建边。
        spill_dependency_checks += len(stream) + 1

    # 每种缓存都是有限整数地址空间，所有区间统一使用 [offset, offset+size)。
    owners = {t: [None] * capacity for t, capacity in CAPACITIES.items()}
    last_release = {t: [None] * capacity for t, capacity in CAPACITIES.items()}
    logical = set()
    ever_allocated = set()
    resident = {}
    pending = {}
    resident_sizes = dict.fromkeys(CAPACITIES, 0)
    resident_peaks = dict.fromkeys(CAPACITIES, 0)
    logical_sizes = dict.fromkeys(CAPACITIES, 0)
    logical_peaks = dict.fromkeys(CAPACITIES, 0)
    high_water = dict.fromkeys(CAPACITIES, 0)
    reuse_barrier_count = 0
    reused_address_units = 0

    def acquire(buf, offset, event_id):
        nonlocal reuse_barrier_count, reused_address_units
        node = alloc[buf]
        t, size = node["Type"], node["Size"]
        end = offset + size
        _require(0 <= offset and end <= CAPACITIES[t],
                 f"节点 {event_id} Buf{buf} 的 {t} 地址 [{offset}, {end}) 越界，容量 {CAPACITIES[t]}")
        _require(buf not in resident, f"节点 {event_id} 重复使 Buf{buf} 驻留")
        barriers = set()
        for address in range(offset, end):
            _require(owners[t][address] is None,
                     f"节点 {event_id} Buf{buf} 与 Buf{owners[t][address]} 在 {t} 地址 {address} 重叠")
            previous = last_release[t][address]
            if previous is not None:
                _require(positions[previous] < positions[event_id],
                         f"物理地址复用屏障不满足：{previous}→{event_id}")
                barriers.add(previous)
                reused_address_units += 1
        reuse_barrier_count += len(barriers)
        for address in range(offset, end):
            owners[t][address] = buf
        resident[buf] = offset
        resident_sizes[t] += size
        resident_peaks[t] = max(resident_peaks[t], resident_sizes[t])
        high_water[t] = max(high_water[t], end)

    def release(buf, event_id):
        _require(buf in resident, f"节点 {event_id} 尝试释放不驻留的 Buf{buf}")
        t, size = alloc[buf]["Type"], alloc[buf]["Size"]
        offset = resident.pop(buf)
        for address in range(offset, offset + size):
            _require(owners[t][address] == buf, f"Buf{buf} 物理地址所有权不一致")
            owners[t][address] = None
            last_release[t][address] = event_id
        resident_sizes[t] -= size

    for node_id in schedule:
        if node_id >= n:
            k, direction = divmod(node_id - n, 2)
            buf, new_offset = spills[k]
            _require(buf in logical, f"SPILL 节点 {node_id} 使用未逻辑分配的 Buf{buf}")
            if direction == 0:
                _require(buf not in pending, f"Buf{buf} 的 SPILL_OUT 重复或交叉")
                release(buf, node_id)
                pending[buf] = k
            else:
                _require(pending.get(buf) == k, f"SPILL_IN 节点 {node_id} 无对应待换入的 SPILL_OUT")
                acquire(buf, new_offset, node_id)
                del pending[buf]
            continue

        node = nodes[node_id]
        if node["Op"] == "ALLOC":
            buf, t, size = node["BufId"], node["Type"], node["Size"]
            _require(buf not in ever_allocated, f"Buf{buf} 重复逻辑申请")
            logical.add(buf)
            ever_allocated.add(buf)
            logical_sizes[t] += size
            logical_peaks[t] = max(logical_peaks[t], logical_sizes[t])
            acquire(buf, memory[buf], node_id)
        elif node["Op"] == "FREE":
            buf, t, size = node["BufId"], node["Type"], node["Size"]
            _require(buf in logical, f"节点 {node_id} FREE 未申请或已释放的 Buf{buf}")
            _require(buf not in pending, f"节点 {node_id} 在 Buf{buf} 尚未 SPILL_IN 时 FREE")
            release(buf, node_id)
            logical.remove(buf)
            logical_sizes[t] -= size
        else:
            for buf in node["Bufs"]:
                _require(buf in logical, f"操作节点 {node_id} 使用未逻辑分配的 Buf{buf}")
                _require(buf in resident, f"操作节点 {node_id} 使用未物理驻留的 Buf{buf}")

    _require(not logical and not resident and not pending, "调度结束时仍有未释放或待换入缓冲区")
    _require(all(value == 0 for value in resident_sizes.values()), "调度结束时物理占用非零")
    spill_counts = Counter()
    extra_by_type = Counter()
    for buf, _ in spills:
        t, size = alloc[buf]["Type"], alloc[buf]["Size"]
        spill_counts[t] += 1
        extra_by_type[t] += size * (1 if buf in copy_in_buffers else 2)
    return {
        "validated": True,
        "nodes": n,
        "edges": len(data["Edges"]),
        "buffers": len(alloc),
        "schedule_nodes": len(schedule),
        "spill_pairs": len(spills),
        "extra_data_movement": sum(extra_by_type.values()),
        "spill_pairs_by_type": {t: spill_counts[t] for t in CAPACITIES},
        "extra_data_by_type": {t: extra_by_type[t] for t in CAPACITIES},
        "peak_resident_by_type": resident_peaks,
        "peak_logical_by_type": logical_peaks,
        "address_high_water_by_type": high_water,
        "spill_dependency_checks": spill_dependency_checks,
        "reuse_barrier_count": reuse_barrier_count,
        "reused_address_units": reused_address_units,
        "capacities": dict(CAPACITIES),
    }


def _read_pairs(path, unique_keys):
    pairs = []
    seen = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split(":")
        _require(len(fields) == 2, f"{path.name} 第 {line_number} 行应为 BufId:Offset")
        try:
            buf, offset = map(int, fields)
        except ValueError as exc:
            raise ValueError(f"{path.name} 第 {line_number} 行包含非整数") from exc
        _require(not unique_keys or buf not in seen,
                 f"{path.name} 第 {line_number} 行重复 BufId {buf}")
        seen.add(buf)
        pairs.append((buf, offset))
    return dict(pairs) if unique_keys else pairs


def read_result_files(results, case):
    """解析官方三文件格式；供命令行与外部独立实验使用。"""
    results = Path(results)
    path = results / f"{case}_schedule.txt"
    schedule = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            schedule.append(int(line.strip()))
        except ValueError as exc:
            raise ValueError(f"{path.name} 第 {line_number} 行不是单个整数 Id") from exc
    memory = _read_pairs(results / f"{case}_memory.txt", unique_keys=True)
    spills = _read_pairs(results / f"{case}_spill.txt", unique_keys=False)
    return schedule, memory, spills


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=Path(DEFAULT_ZIP))
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--case", default="all")
    args = parser.parse_args()
    report = {}
    failures = 0
    with zipfile.ZipFile(args.zip) as archive:
        names = sorted(name for name in archive.namelist()
                       if name.endswith(".json")
                       and (args.case == "all" or Path(name).stem == args.case))
        if not names:
            parser.error(f"ZIP 中未找到算例 {args.case!r}")
        for name in names:
            case = Path(name).stem
            try:
                data = json.loads(archive.read(name))
                schedule, memory, spills = read_result_files(args.results, case)
                report[case] = verify_case(data, schedule, memory, spills)
                print(f"{case}: validated=True, spills={report[case]['spill_pairs']}, "
                      f"extra_data={report[case]['extra_data_movement']}", flush=True)
            except (ValueError, OSError) as exc:
                failures += 1
                report[case] = {"validated": False, "error": str(exc)}
                print(f"{case}: validated=False, error={exc}", flush=True)
    args.results.mkdir(parents=True, exist_ok=True)
    (args.results / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
