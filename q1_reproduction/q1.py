"""问题一教学复现：拓扑启发式初始解 + 合法重插入模拟退火。仅依赖标准库。
正文方法的独立实现，非作者完整源代码；默认按题面统计全部缓存类型。
"""
import argparse
import heapq
from itertools import accumulate
import json
import math
import random
import zipfile
from pathlib import Path

DEFAULT_ZIP = r'D:/BaiduNetdiskDownload/华为杯/真题/2025年年中国研究生数学建模竞赛赛题/A题/通用神经网络处理器下的核内调度问题附件.zip'

class Graph:
    def __init__(self, data, l0_single=False, objective="all", paper_score=False):
        self.l0_single = l0_single
        self.objective = objective
        self.paper_score = paper_score
        self.nodes = {v['Id']: v for v in data['Nodes']}
        assert len(self.nodes) == len(data['Nodes']), '重复节点'
        self.edges = list(dict.fromkeys(map(tuple, data['Edges'])))
        self.succ = {v: [] for v in self.nodes}
        self.pred = {v: [] for v in self.nodes}
        for u, v in self.edges:
            self.succ[u].append(v)
            self.pred[v].append(u)
        self.weight = {v: (n['Size'] if n['Op']=='ALLOC' else
                          -n['Size'] if n['Op']=='FREE' else 0)
                       for v,n in self.nodes.items()}
        # 原始weight用于生命周期检查；objective_weight决定优化和报告口径。
        self.objective_weight = {
            v: w if objective == 'all' or self.nodes[v].get('Type') in ('L1','UB') else 0
            for v,w in self.weight.items()}
        self.height = dict.fromkeys(self.nodes, 0)
        for v in reversed(self.initial('id', enforce_l0=False)):
            self.height[v] = max((1+self.height[u] for u in self.succ[v]), default=0)

    def dfs_rank(self, root_order):
        """扩展DFS：从FREE节点反向深搜前驱，形成拓扑优先序。

        正文算法3沿后继前向遍历，附录没有给出完整DFS实现。这里反向遍历
        属于我们的可选扩展，统一尝试四种根排序及指定数量的根前置。
        """
        front_index = int(root_order[6:]) if root_order.startswith('front_') else None
        if front_index is not None:
            root_order='id_desc'
        by_size = root_order.startswith('size')
        reverse = root_order.endswith('desc')
        roots = sorted((v for v in self.nodes if self.nodes[v]['Op']=='FREE'),
                       key=(lambda v:(self.nodes[v].get('Size',0),v)) if by_size else None,
                       reverse=reverse)
        if front_index is not None and front_index < len(roots):
            roots.insert(0,roots.pop(front_index))
        done=set(); result=[]
        for v in roots:
            stack=[(v,False)]
            while stack:
                u,finished=stack.pop()
                if u in done: continue
                if finished:
                    done.add(u); result.append(u)
                else:
                    stack.append((u,True))
                    stack.extend((p,False) for p in sorted(self.pred[u],reverse=True) if p not in done)
        for v in self.initial('id',enforce_l0=False):
            if v not in done: result.append(v)
        return {v:i for i,v in enumerate(result)}

    def initial(self, strategy, enforce_l0=None):
        """论文算法2—4：Kahn拓扑排序，按优先级从可执行节点中选择。

        L0约束使用三个独立候选堆；被占用时暂停该类ALLOC，不丢弃节点。
        每个节点只入堆/出堆一次，避免附录每轮全图扫描的二次复杂度。
        """
        if enforce_l0 is None:
            enforce_l0 = self.l0_single
        rank = self.dfs_rank(strategy[4:]) if strategy.startswith('dfs_') else None
        degree = {v: len(p) for v,p in self.pred.items()}
        queues = {t: [] for t in ('general','L0A','L0B','L0C')}
        active = dict.fromkeys(('L0A','L0B','L0C'))
        order = []
        serial = 0
        def push(v):
            nonlocal serial
            n = self.nodes[v]
            if strategy == 'greedy':
                impact = self.weight[v]
                if self.paper_score and n.get('Type') not in ('L1','UB'):
                    impact = 0
                key = (n['Op'] != 'FREE', impact, v)
            elif strategy == 'critical':
                # 附录第48页优先级；height按到终点的最长边数计算。
                key = (n['Op'] != 'FREE', -self.height[v], n['Op']=='ALLOC', v)
            elif rank is not None:
                key = (n['Op'] != 'FREE', rank[v], v)
            elif strategy == 'depth':
                key = (-serial, v)
            else:
                key = (v,)
            serial += 1
            q = n.get('Type') if enforce_l0 and n['Op']=='ALLOC' and n.get('Type') in active else 'general'
            heapq.heappush(queues[q], (key,v))
        for v in sorted(self.nodes):
            if degree[v] == 0:
                push(v)
        while len(order) < len(self.nodes):
            eligible = [(q[0],t) for t,q in queues.items()
                        if q and (t=='general' or active[t] is None)]
            if not eligible:
                raise ValueError('无合法就绪节点：图中有环或当前L0选择导致死锁；不能强行调度')
            _,qname = min(eligible)
            _,v = heapq.heappop(queues[qname])
            n = self.nodes[v]
            if enforce_l0 and n.get('Type') in active:
                t = n['Type']
                if n['Op']=='ALLOC':
                    active[t] = n['BufId']
                elif n['Op']=='FREE':
                    assert active[t] == n['BufId']
                    active[t] = None
            order.append(v)
            for u in self.succ[v]:
                degree[u] -= 1
                if degree[u] == 0:
                    push(u)
        return order

    def peak(self, order):
        """论文5.3的目标M：各步累计驻留量的最大值。"""
        return max(accumulate(map(self.objective_weight.__getitem__, order), initial=0))

    def validate(self, order):
        """独立校验排列、每条依赖边和每个缓冲区的实际生命周期。"""
        assert len(order)==len(self.nodes) and set(order)==set(self.nodes)
        pos = {v:i for i,v in enumerate(order)}
        assert all(pos[u]<pos[v] for u,v in self.edges), '非拓扑序'
        live = {}
        stay = peak = 0
        per_type = {}
        l0_active = {}
        type_peak = {}
        for v in order:
            n = self.nodes[v]
            if n['Op']=='ALLOC':
                b=n['BufId']; assert b not in live
                if self.l0_single and n['Type'] in ('L0A','L0B','L0C'):
                    assert n['Type'] not in l0_active, ('L0重叠', v)
                    l0_active[n['Type']] = b
                live[b]=(n['Type'], n['Size'])
                per_type[n['Type']]=per_type.get(n['Type'],0)+n['Size']
            elif n['Op']=='FREE':
                b=n['BufId']; assert b in live
                if self.l0_single and n['Type'] in ('L0A','L0B','L0C'):
                    assert l0_active.pop(n['Type']) == b
                assert live.pop(b)==(n['Type'],n['Size'])
                per_type[n['Type']]-=n['Size']
            else:
                assert all(b in live for b in n.get('Bufs',[])), ('缓冲区未存活', v)
            stay += self.weight[v]
            assert stay>=0
            peak=max(peak,stay)
            for t,s in per_type.items():
                type_peak[t]=max(type_peak.get(t,0),s)
        assert not live and stay==0
        if self.objective=='all':
            assert peak==self.peak(order)
        return type_peak

    def compact(self, order):
        """补充改进（不是论文原伪代码）：延后ALLOC，再提前FREE。

        保持其他节点的相对顺序，仅收缩生命周期。对应论文合法重插入
        邻域的定向边界移动；不会增加峰值，且保留原序列L0可行性。
        """
        def postpone(sequence, op, dependencies):
            done=set(); result=[]
            def emit(v):
                stack=[(v,False)]
                while stack:
                    u,finished=stack.pop()
                    if u in done: continue
                    if finished:
                        done.add(u); result.append(u)
                    else:
                        stack.append((u,True))
                        stack.extend((p,False) for p in dependencies[u] if p not in done)
            for v in sequence:
                if self.nodes[v]['Op'] != op: emit(v)
            for v in sequence: emit(v)
            return result
        result=postpone(order,'ALLOC',self.pred)
        result=postpone(result[::-1],'FREE',self.succ)[::-1]
        self.validate(result)
        assert self.peak(result) <= self.peak(order)
        return result

    def anneal(self, initial, iterations=2000, seed=2025):
        """论文算法1：合法重插入 + Metropolis准则 + 几何降温。

        论文未给完整参数，当前参数见report。L0模式增加FREE→下一ALLOC边，
        保持初始L0缓冲区顺序；一次合法单节点移动也无法交换两个L0区间。
        """
        rng=random.Random(seed)
        order=initial.copy(); best=order.copy()
        cost=best_cost=self.peak(order)
        ids=sorted(self.nodes)
        cumweights=list(accumulate(4 if not self.pred[v] or not self.succ[v] else 1 for v in ids))
        pred={v:p.copy() for v,p in self.pred.items()}
        succ={v:p.copy() for v,p in self.succ.items()}
        if self.l0_single:
            last_free={}
            for v in initial:
                n=self.nodes[v]; t=n.get('Type')
                if t not in ('L0A','L0B','L0C'): continue
                if n['Op']=='ALLOC' and t in last_free:
                    u=last_free[t]
                    if u not in pred[v]:
                        pred[v].append(u); succ[u].append(v)
                elif n['Op']=='FREE':
                    last_free[t]=v
        temperature0=max(1.0,cost*0.05)
        trace=[]
        accepted=improvements=moved=0
        positions={u:i for i,u in enumerate(order)}
        for step in range(iterations):
            v=rng.choices(ids,cum_weights=cumweights,k=1)[0]
            old=positions[v]
            # 删除v后的索引：原来位于其右侧的节点索引减1。
            left=max((positions[u]-(positions[u]>old)+1 for u in pred[v]),default=0)
            right=min((positions[u]-(positions[u]>old) for u in succ[v]),default=len(order)-1)
            dest=rng.randint(left,right)
            if dest != old:
                moved+=1
                candidate=order.copy()
                candidate.insert(dest,candidate.pop(old))
                new_cost=self.peak(candidate)
                temperature=temperature0*(0.01/temperature0)**(step/max(1,iterations-1))
                delta=new_cost-cost
                if delta<=0 or rng.random()<math.exp(-delta/temperature):
                    order,cost=candidate,new_cost
                    for j in range(min(old,dest),max(old,dest)+1):
                        positions[order[j]]=j
                    accepted+=1
                    if cost<best_cost:
                        best,best_cost=order.copy(),cost
                        improvements+=1
            if step%1000==0 or step==iterations-1:
                trace.append({'step':step+1,'current':cost,'best':best_cost,
                              'moved':moved,'accepted':accepted,'improvements':improvements})
        return best,trace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip',default=DEFAULT_ZIP)
    parser.add_argument('--case',default='FlashAttention_Case0',help='任务名或 all')
    parser.add_argument('--iterations',type=int,default=2000)
    parser.add_argument('--seed',type=int,default=2025)
    parser.add_argument('--dfs-root-trials',type=int,default=0,help='统一尝试将FREE降序列表中第2至第K+1个根前置，属于额外多起点改进')
    parser.add_argument('--dfs-variants',action='store_true',help='启用我们扩展的反向DFS，统一尝试四种根排序')
    parser.add_argument('--compact',action='store_true',help='启用我们补充的生命周期收缩改进')
    parser.add_argument('--l0-single',action='store_true',help='采用论文每类L0同时一个缓冲区约束')
    parser.add_argument('--objective',choices=('all','l1ub'),default='all',help='all按题面公式；l1ub按论文第9页特殊假设')
    parser.add_argument('--paper-score',action='store_true',help='贪心优先级的memory_impact只统计L1/UB，见附录46页')
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'results')
    args=parser.parse_args()
    if args.iterations<0 or args.dfs_root_trials<0: parser.error('尝试次数必须非负')
    args.out.mkdir(parents=True,exist_ok=True)
    report={}
    with zipfile.ZipFile(args.zip) as archive:
        names=sorted(n for n in archive.namelist() if n.endswith('.json') and
                     (args.case=='all' or Path(n).stem==args.case))
        if not names: raise ValueError('未找到指定算例')
        for name in names:
            g=Graph(json.loads(archive.read(name)), args.l0_single, args.objective, args.paper_score)
            initial={}; failed={}
            strategies=['id','greedy','depth','critical']
            if args.dfs_variants:
                strategies += ['dfs_id_asc','dfs_id_desc','dfs_size_asc','dfs_size_desc']
            root_count=sum(n['Op']=='FREE' for n in g.nodes.values())
            strategies += [f'dfs_front_{i}' for i in range(1,min(args.dfs_root_trials+1,root_count))]
            for strategy in strategies:
                try:
                    order=g.initial(strategy)
                    g.validate(order)
                    initial[strategy]=order
                except ValueError as error:
                    failed[strategy]=str(error)
            if not any(s != 'id' for s in initial):
                raise ValueError(f'{name}: 所有启发式均无法生成完整序列')
            raw_peaks={s:g.peak(order) for s,order in initial.items()}
            if args.compact:
                initial={s:g.compact(order) for s,order in initial.items()}
            peaks={s:g.peak(order) for s,order in initial.items()}
            chosen=min((s for s in initial if s != 'id'),key=lambda s:peaks[s])
            best,trace=g.anneal(initial[chosen],args.iterations,args.seed)
            by_type=g.validate(best)
            case=Path(name).stem
            (args.out/f'{case}_schedule.txt').write_text('\n'.join(map(str,best))+'\n',encoding='utf-8')
            report[case]={'nodes':len(g.nodes),'edges':len(g.edges),
                          'raw_initial_peaks':raw_peaks,'initial_peaks':peaks,'compact':args.compact,'dfs_variants':args.dfs_variants,'dfs_root_trials':args.dfs_root_trials,'chosen':chosen,'final_peak':g.peak(best),
                          'per_type_peaks':by_type,'valid':True,
                          'seed':args.seed,'iterations':args.iterations,'trace':trace,
                          'objective':args.objective,'l0_single':args.l0_single,
                          'paper_score':args.paper_score,'failed_initializations':failed,
                          'parameters':{'T_initial':max(1.0,peaks[chosen]*0.05),'T_final':0.01,
                                        'boundary_weight':4,'other_weight':1},
                          'scope':'DAG and buffer lifetimes; optional L0 exclusivity; no L1/UB capacity limits'}
            print(case, 'strategy=',chosen, 'initial=',peaks[chosen], 'final=',g.peak(best), 'validated=True',flush=True)
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    main()
