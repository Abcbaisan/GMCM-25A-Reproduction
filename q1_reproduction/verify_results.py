import json
import argparse
from collections import defaultdict
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description='独立读取源数据和已保存调度结果进行验证，不调用Graph校验函数')
parser.add_argument('--results',type=Path,default=root/'reproduction_results')
parser.add_argument('--zip',type=Path,default=Path('D:/BaiduNetdiskDownload/华为杯/真题/2025年年中国研究生数学建模竞赛赛题/A题/通用神经网络处理器下的核内调度问题附件.zip'))
args=parser.parse_args()
archive_path=args.zip
with zipfile.ZipFile(archive_path) as archive:
    sources={Path(name).stem:json.loads(archive.read(name)) for name in archive.namelist() if name.endswith('.json')}

for directory in [args.results]:
    if not (directory/'report.json').exists(): raise FileNotFoundError(directory/'report.json')
    report=json.loads((directory/'report.json').read_text(encoding='utf8'))
    verified={}
    for case,entry in report.items():
        order=list(map(int,(directory/f'{case}_schedule.txt').read_text(encoding='utf8').split()))
        source=sources[case]; nodes={n['Id']:n for n in source['Nodes']}
        pos={v:i for i,v in enumerate(order)}
        assert len(pos)==len(order)==len(nodes) and set(pos)==set(nodes)
        assert all(pos[u]<pos[v] for u,v in source['Edges'])
        live={}; active={}; occupation=defaultdict(int); typepeaks=defaultdict(int)
        total=lu=allpeak=lupeak=0
        for v in order:
            n=nodes[v]
            if n['Op']=='ALLOC':
                b=n['BufId'];t=n['Type'];s=n['Size']
                assert b not in live
                if entry.get('l0_single') and t in ('L0A','L0B','L0C'):
                    assert t not in active, (directory,case,'L0 overlap',v)
                    active[t]=b
                live[b]=(t,s)
                total+=s
                if t in ('L1','UB'):lu+=s
                occupation[t]+=s
                typepeaks[t]=max(typepeaks[t],occupation[t])
            elif n['Op']=='FREE':
                b=n['BufId'];t=n['Type'];s=n['Size']
                assert live.pop(b)==(t,s)
                if entry.get('l0_single') and t in ('L0A','L0B','L0C'):assert active.pop(t)==b
                total-=s
                if t in ('L1','UB'):lu-=s
                occupation[t]-=s
            else:
                assert all(b in live for b in n.get('Bufs',[])), (directory,case,'lifecycle',v)
            allpeak=max(allpeak,total);lupeak=max(lupeak,lu)
        assert not live and not active and total==lu==0
        expected=lupeak if entry.get('objective')=='l1ub' else allpeak
        assert entry['final_peak']==expected,(directory,case,entry['final_peak'],expected)
        assert entry['per_type_peaks']==dict(typepeaks)
        verified[case]={'all':allpeak,'l1ub':lupeak}
    (directory/'independent_validation.json').write_text(json.dumps(verified,indent=2),encoding='utf-8')
    print('全部通过独立校验：',json.dumps(verified,ensure_ascii=False),flush=True)
