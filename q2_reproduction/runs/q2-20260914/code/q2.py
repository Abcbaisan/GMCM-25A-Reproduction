"""问题二：固定原缓存类型，连续地址分配与延迟SPILL_IN。
独立教学实现论文算法5—7的可执行部分；paper-small/large对应附录/正文的不同描述。
不实现会改变Type的映射或未给完整模型的ILP，farthest/cost-distance为补充启发式。
"""
import argparse
from bisect import bisect_left
from collections import defaultdict
import json
from pathlib import Path
import time
import zipfile

CAPACITIES = {'L1':4096, 'UB':1024, 'L0A':256, 'L0B':256, 'L0C':512}
DEFAULT_ZIP = r'D:/BaiduNetdiskDownload/华为杯/真题/2025年年中国研究生数学建模竞赛赛题/A题/通用神经网络处理器下的核内调度问题附件.zip'
DEFAULT_Q1 = Path(__file__).resolve().parents[1]/'q1_reproduction/reproduction_results'


class MemoryPool:
    """空闲区间表，地址为半开区间[offset, offset+size)。"""
    def __init__(self, capacity, placement='best-fit'):
        self.capacity = capacity
        self.placement = placement
        self.holes = [(0, capacity)]

    def allocate(self, size):
        choices = [(length, start, i) for i,(start,length) in enumerate(self.holes) if length >= size]
        if not choices:
            return None
        if self.placement == 'best-fit':
            _,start,i = min(choices)
        else:
            _,start,i = min(choices,key=lambda x:x[1])
        old_start,length = self.holes[i]
        if length == size:
            self.holes.pop(i)
        else:
            self.holes[i] = (old_start+size,length-size)
        return start

    def release(self, offset, size):
        self.holes.append((offset,size))
        merged = []
        for start,length in sorted(self.holes):
            if merged and merged[-1][0]+merged[-1][1] == start:
                prev,size0 = merged[-1]
                merged[-1] = (prev,size0+length)
            else:
                if merged and merged[-1][0]+merged[-1][1] > start:
                    raise ValueError('释放区间重叠')
                merged.append((start,length))
        self.holes = merged


class SpillAllocator:
    def __init__(self, data, order, policy='paper-small', placement='best-fit'):
        self.nodes = {n['Id']:n for n in data['Nodes']}
        self.order = list(order)
        self.n = len(self.nodes)
        if set(self.nodes) != set(range(self.n)):
            raise ValueError('本题要求原节点Id为0至N-1')
        if len(self.order) != self.n or set(self.order) != set(self.nodes):
            raise ValueError('输入调度节点不完整或重复')
        pos = {v:i for i,v in enumerate(order)}
        if any(pos[u]>=pos[v] for u,v in data['Edges']):
            raise ValueError('输入调度不满足拓扑序')
        self.buffers = {}
        for n in data['Nodes']:
            if n['Op']=='ALLOC':
                b=n['BufId']
                if b in self.buffers: raise ValueError('重复申请节点')
                self.buffers[b]={'type':n['Type'],'size':n['Size'],'alloc':n['Id']}
                if not 0<n['Size']<=CAPACITIES[n['Type']]:
                    raise ValueError('单个缓冲区超出容量或Size非法')
        for n in data['Nodes']:
            if n['Op']=='FREE': self.buffers[n['BufId']]['free']=n['Id']
        self.copyin={b for n in data['Nodes'] if n['Op']=='COPY_IN' for b in n.get('Bufs',[])}
        self.uses=defaultdict(list)
        live=set()
        for p,v in enumerate(order):
            n=self.nodes[v]
            if n['Op']=='ALLOC':
                live.add(n['BufId'])
            elif n['Op']=='FREE':
                b=n['BufId']
                if b not in live: raise ValueError('先释放后申请')
                live.remove(b)
                self.uses[b].append(p)  # 无后续操作时也必须在FREE前换入。
            else:
                required=set(n.get('Bufs',[]))
                if not required <= live: raise ValueError('输入序列缓冲区生命周期非法')
                required_sizes=defaultdict(int)
                for b in required:
                    info=self.buffers[b]
                    required_sizes[info['type']]+=info['size']
                    self.uses[b].append(p)
                if any(s>CAPACITIES[t] for t,s in required_sizes.items()):
                    raise ValueError(f'节点{v}同类型同时所需缓存超过容量')
        if live: raise ValueError('输入存在未释放缓冲区')
        self.policy=policy
        self.placement=placement
        self.pools={t:MemoryPool(c,placement) for t,c in CAPACITIES.items()}
        self.active=set()                 # 逻辑生命周期已开始且尚未FREE
        self.resident={}                 # 当前确实在核内：BufId -> Offset
        self.resident_by_type={t:set() for t in CAPACITIES}
        self.pending={}                  # 已OUT未IN：BufId -> spill记录索引
        self.memory={}                   # 每个原ALLOC获得的起始Offset
        self.spills=[]                   # OUT发生顺序，决定新增节点编号
        self.schedule=[]
        self.extra=0
        self.repack_count=0
        self.capacity_failures=0
        self.fragmentation_failures=0
        self.position=0

    def next_use(self,b):
        positions=self.uses[b]
        i=bisect_left(positions,self.position)
        return positions[i] if i<len(positions) else len(self.order)+1

    def choose_victim(self,typ,protected):
        candidates=self.resident_by_type[typ]-protected
        if not candidates:
            raise ValueError(f'位置{self.position}没有可换出缓冲区；工作集或碎片布局不可行')
        def priority(b):
            size=self.buffers[b]['size']
            copied=b in self.copyin
            distance=max(1,self.next_use(b)-self.position)
            if self.policy=='paper-small':
                return (not copied,size,b)        # 附录第51页
            if self.policy=='paper-large':
                return (not copied,-size,b)       # 正文第25页
            if self.policy=='farthest':
                return (-distance,not copied,-size,b)
            # 每单位可释放空间的搬运代价为1或2，结合下一次使用距离。
            return (-distance/(1 if copied else 2),-size,b)
        return min(candidates,key=priority)

    def spill_out(self,b):
        info=self.buffers[b]
        k=len(self.spills)
        out_id,in_id=self.n+2*k,self.n+2*k+1
        cost=info['size']*(1 if b in self.copyin else 2)
        record={'buf':b,'out_id':out_id,'in_id':in_id,'new_offset':None,
                'old_offset':self.resident[b],'cost':cost,
                'out_cycles':0 if b in self.copyin else 2*info['size']+150,
                'in_cycles':2*info['size']+150,'before_original_position':self.position}
        self.spills.append(record)
        self.pending[b]=k
        self.schedule.append(out_id)
        self.pools[info['type']].release(self.resident.pop(b),info['size'])
        self.resident_by_type[info['type']].remove(b)
        self.extra+=cost

    def acquire(self,b,protected):
        info=self.buffers[b]
        pool=self.pools[info['type']]
        offset=pool.allocate(info['size'])
        if offset is None:
            if sum(length for _,length in pool.holes)>=info['size']:
                self.fragmentation_failures+=1
            else:
                self.capacity_failures+=1
        while offset is None:
            victim=self.choose_victim(info['type'],protected)
            self.spill_out(victim)
            offset=pool.allocate(info['size'])
        self.resident[b]=offset
        self.resident_by_type[info['type']].add(b)
        return offset

    def restore(self,b,protected):
        if b in self.resident: return
        if b not in self.pending: raise ValueError('缓冲区未申请或未被换出，不能换入')
        # 分配目标地址可能换出别的缓冲区，但不能换出当前操作需要的任何Buf。
        offset=self.acquire(b,protected)
        k=self.pending.pop(b)
        self.spills[k]['new_offset']=offset
        self.schedule.append(self.spills[k]['in_id'])

    def can_place_needed(self,typ,needed):
        missing=needed-set(self.resident)
        if not missing: return True
        probe=MemoryPool(CAPACITIES[typ],self.placement)
        # 把固定住的区间从可用连续空间中扣除；其他buffer理论上可被换出。
        intervals=sorted((self.resident[b],self.buffers[b]['size']) for b in needed if b in self.resident)
        probe.holes=[];end=0
        for off,size in intervals:
            if off>end: probe.holes.append((end,off-end))
            end=off+size
        if end<CAPACITIES[typ]: probe.holes.append((end,CAPACITIES[typ]-end))
        return all(probe.allocate(self.buffers[b]['size']) is not None
                   for b in sorted(missing,key=lambda x:(-self.buffers[x]['size'],x)))

    def repack(self,typ,needed):
        # 真实换出本类型所有驻留buffer，使下一操作需要的buffer可紧凑重载。
        # 这是保守恢复措施，产生的每一次OUT/IN都计入正式SPILL成本。
        self.repack_count+=1
        for b in sorted(self.resident_by_type[typ]):
            self.spill_out(b)
        for b in sorted(needed,key=lambda x:(-self.buffers[x]['size'],x)):
            self.restore(b,needed)

    def run(self):
        for self.position,v in enumerate(self.order):
            n=self.nodes[v]
            if n['Op']=='ALLOC':
                b=n['BufId']
                offset=self.acquire(b,{b})
                self.memory[b]=offset
                self.active.add(b)
                self.schedule.append(v)
            elif n['Op']=='FREE':
                b=n['BufId']
                self.restore(b,{b})
                self.schedule.append(v)
                info=self.buffers[b]
                self.pools[info['type']].release(self.resident.pop(b),info['size'])
                self.resident_by_type[info['type']].remove(b)
                self.active.remove(b)
            else:
                protected=set(n.get('Bufs',[]))
                for b in sorted(protected,key=lambda x:(-self.buffers[x]['size'],x)):
                    typ=self.buffers[b]['type']
                    needed={u for u in protected if self.buffers[u]['type']==typ}
                    # 每次换入前重新检查；之前刚放好的buffer可能改变碎片布局。
                    if not self.can_place_needed(typ,needed):
                        self.repack(typ,needed)
                    self.restore(b,protected)
                self.schedule.append(v)
        if self.active or self.resident or self.pending:
            raise ValueError('结束后仍有未完成的缓冲区生命周期/SPILL')
        if any(p.holes != [(0,p.capacity)] for p in self.pools.values()):
            raise ValueError('内存未完整归还')
        return {'schedule':self.schedule,'memory':self.memory,
                'spills':[(r['buf'],r['new_offset']) for r in self.spills],
                'events':self.spills,'additional_transfer':self.extra,
                'spill_count':len(self.spills),'policy':self.policy,'placement':self.placement,
                'capacity_failures':self.capacity_failures,'fragmentation_failures':self.fragmentation_failures,
                'repack_count':self.repack_count}


def save_result(directory,case,result):
    directory.mkdir(parents=True,exist_ok=True)
    (directory/f'{case}_schedule.txt').write_text('\n'.join(map(str,result['schedule']))+'\n',encoding='utf-8')
    (directory/f'{case}_memory.txt').write_text(''.join(f'{b}:{off}\n' for b,off in sorted(result['memory'].items())),encoding='utf-8')
    (directory/f'{case}_spill.txt').write_text(''.join(f'{b}:{off}\n' for b,off in result['spills']),encoding='utf-8')
    (directory/f'{case}_events.json').write_text(json.dumps(result['events'],indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip',default=DEFAULT_ZIP)
    parser.add_argument('--schedule-dir',type=Path,default=DEFAULT_Q1)
    parser.add_argument('--case',default='all')
    parser.add_argument('--policy',choices=['all','paper-small','paper-large','farthest','cost-distance'],default='all')
    parser.add_argument('--placement',choices=['all','best-fit','first-fit'],default='all')
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'results')
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    from verify_q2 import verify_case
    policies=['paper-small','paper-large','farthest','cost-distance'] if args.policy=='all' else [args.policy]
    placements=['best-fit','first-fit'] if args.placement=='all' else [args.placement]
    report={}
    with zipfile.ZipFile(args.zip) as archive:
        names=sorted(n for n in archive.namelist() if n.endswith('.json') and (args.case=='all' or Path(n).stem==args.case))
        if not names: raise ValueError('未找到算例')
        for name in names:
            case=Path(name).stem
            data=json.loads(archive.read(name))
            order=list(map(int,(args.schedule_dir/f'{case}_schedule.txt').read_text(encoding='utf-8').split()))
            trials=[];best=None
            for policy in policies:
                for placement in placements:
                    started=time.perf_counter()
                    try:
                        result=SpillAllocator(data,order,policy,placement).run()
                        validation=verify_case(data,result['schedule'],result['memory'],result['spills'])
                        if validation['extra_data_movement']!=result['additional_transfer']:
                            raise ValueError('求解器搬运量与独立重算不一致')
                        trial={k:result[k] for k in ('policy','placement','additional_transfer','spill_count','capacity_failures','fragmentation_failures','repack_count')}
                        trial['seconds']=round(time.perf_counter()-started,4)
                        trial['valid']=True
                        trials.append(trial)
                        if best is None or (result['additional_transfer'],result['spill_count'])<(best['additional_transfer'],best['spill_count']):
                            best=result
                    except ValueError as error:
                        trials.append({'policy':policy,'placement':placement,'error':str(error),'valid':False})
            if best is None: raise ValueError(f'{case}: 所有策略失败，详见{trials}')
            save_result(args.out,case,best)
            report[case]={k:best[k] for k in ('policy','placement','additional_transfer','spill_count','capacity_failures','fragmentation_failures','repack_count')}
            report[case].update({'source_schedule':str((args.schedule_dir/f'{case}_schedule.txt').resolve()),
                'original_nodes':len(data['Nodes']),'expanded_nodes':len(best['schedule']),
                'preserves_original_order':True,'capacities':CAPACITIES,'trials':trials,
                'validation':verify_case(data,best['schedule'],best['memory'],best['spills'])})
            print(case,best['policy'],best['placement'],'transfer=',best['additional_transfer'],'spills=',best['spill_count'],flush=True)
            (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    main()
