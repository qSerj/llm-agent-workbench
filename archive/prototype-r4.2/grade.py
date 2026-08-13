#!/usr/bin/env python3
from pathlib import Path
import argparse,json,re,subprocess
def sh(c,cwd): return subprocess.run(c,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout
def has(p,*xs):
    if not p.exists(): return False
    s=p.read_text(encoding="utf-8",errors="replace")
    return all(re.search(x,s,re.I|re.S) for x in xs)
def main():
    a=argparse.ArgumentParser(); a.add_argument("workspace"); a.add_argument("--task",type=int,required=True); x=a.parse_args(); ws=Path(x.workspace); C=[]
    def add(n,ok,pts): C.append({"name":n,"ok":bool(ok),"points":pts if ok else 0,"max_points":pts})
    add("source_unchanged",sh(["git","diff","--","src"],ws).strip()=="",5)
    if x.task==1:
      p=ws/"docs/01-interleavers.md"; add("doc",p.exists(),2); add("interface",has(p,"IInterleaverProfile"),1); add("simple_limits",has(p,r"\b2\b",r"\b16\b"),2); add("table_limits",has(p,r"\b2\b",r"\b32\b"),2); add("encoding",has(p,"BranchCount","DelayStepSymbols","register"),2); add("usage",has(p,"ProfileUsageExample|ConfigureDefaultAsync"),2)
    elif x.task==2:
      p=ws/"docs/02-apply-behavior.md"; add("doc",p.exists(),2); add("repeat_skip",has(p,"false|skip|no .*write|not .*write"),3); add("encoded_equality",has(p,"register","SequenceEqual|encoded|value"),2); add("cmd",has(p,"0x42"),2); add("cache_after",has(p,"cache|_lastAppliedRegisters","after|success"),3); add("throw",has(p,"throw|exception","cache|not .*updated|unchanged"),3)
    else:
      p=ws/"docs/03-public-api.md"; add("doc",p.exists(),2); add("profiles",has(p,"SimpleInterleaverProfile","TableInterleaverProfile"),2); add("constraints",has(p,r"\b16\b",r"\b32\b",r"non.?negative|>=\s*0|negative"),2); add("return",has(p,"ApplyInterleaverProfile","true","false"),2); add("unknown",has(p,"Unknown from this repository"),2)
    print(json.dumps({"task":x.task,"score":sum(c["points"] for c in C),"max_score":sum(c["max_points"] for c in C),"checks":C},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
