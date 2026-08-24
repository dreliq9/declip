#!/usr/bin/env python3
import ctypes, hashlib, json, os, random, statistics, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MK_OK, MK_INVALID, MK_NOT_FOUND, MK_CONFLICT, MK_OVERFLOW, MK_STALE, MK_CYCLE = 0, 1, 2, 3, 5, 6, 7
SRC, XFORM, SINK = 1, 2, 3
NO_SLOT = 0xFFFFFFFF

class Time(ctypes.Structure):
    _fields_ = [("num", ctypes.c_int64), ("den", ctypes.c_int64)]

class Handle(ctypes.Structure):
    _fields_ = [("slot", ctypes.c_uint32), ("generation", ctypes.c_uint32)]

NO_RESOURCE = Handle(NO_SLOT, 0)

def load(path):
    lib = ctypes.CDLL(str(Path(path).resolve()))
    lib.mk_time_normalize.argtypes=[Time,ctypes.POINTER(Time)]; lib.mk_time_normalize.restype=ctypes.c_int
    lib.mk_time_add.argtypes=[Time,Time,ctypes.POINTER(Time)]; lib.mk_time_add.restype=ctypes.c_int
    lib.mk_time_compare.argtypes=[Time,Time]; lib.mk_time_compare.restype=ctypes.c_int
    lib.mk_kernel_create.restype=ctypes.c_void_p
    lib.mk_kernel_destroy.argtypes=[ctypes.c_void_p]
    lib.mk_kernel_revision.argtypes=[ctypes.c_void_p]; lib.mk_kernel_revision.restype=ctypes.c_uint64
    lib.mk_kernel_add_asset.argtypes=[ctypes.c_void_p,ctypes.c_char_p,Time]; lib.mk_kernel_add_asset.restype=ctypes.c_int
    lib.mk_kernel_append_clip.argtypes=[ctypes.c_void_p,ctypes.c_char_p,Time,Time,Time]; lib.mk_kernel_append_clip.restype=ctypes.c_int
    lib.mk_kernel_propose_trim.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_size_t,Time,ctypes.POINTER(ctypes.c_uint64)]; lib.mk_kernel_propose_trim.restype=ctypes.c_int
    lib.mk_kernel_commit.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint64)]; lib.mk_kernel_commit.restype=ctypes.c_int
    lib.mk_kernel_state_hash.argtypes=[ctypes.c_void_p]; lib.mk_kernel_state_hash.restype=ctypes.c_uint64
    lib.mk_resource_alloc.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint32,ctypes.POINTER(Handle)]; lib.mk_resource_alloc.restype=ctypes.c_int
    lib.mk_resource_retain.argtypes=[ctypes.c_void_p,Handle]; lib.mk_resource_retain.restype=ctypes.c_int
    lib.mk_resource_release.argtypes=[ctypes.c_void_p,Handle]; lib.mk_resource_release.restype=ctypes.c_int
    lib.mk_resource_touch.argtypes=[ctypes.c_void_p,Handle]; lib.mk_resource_touch.restype=ctypes.c_int
    lib.mk_resource_refcount.argtypes=[ctypes.c_void_p,Handle,ctypes.POINTER(ctypes.c_uint32)]; lib.mk_resource_refcount.restype=ctypes.c_int
    lib.mk_resource_hash.argtypes=[ctypes.c_void_p]; lib.mk_resource_hash.restype=ctypes.c_uint64
    lib.mk_plan_reset.argtypes=[ctypes.c_void_p]; lib.mk_plan_reset.restype=ctypes.c_int
    lib.mk_plan_add_node.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_size_t,Handle]; lib.mk_plan_add_node.restype=ctypes.c_int
    lib.mk_plan_validate.argtypes=[ctypes.c_void_p]; lib.mk_plan_validate.restype=ctypes.c_int
    lib.mk_plan_hash.argtypes=[ctypes.c_void_p]; lib.mk_plan_hash.restype=ctypes.c_uint64
    lib.mk_ffmpeg_version.restype=ctypes.c_uint32
    lib.mk_benchmark.argtypes=[ctypes.c_uint64]; lib.mk_benchmark.restype=ctypes.c_uint64
    return lib

def add_node(lib,k,node_id,kind,deps,resource=NO_RESOURCE):
    if deps:
        arr=(ctypes.c_uint32*len(deps))(*deps)
        return int(lib.mk_plan_add_node(k,node_id,kind,arr,len(deps),resource))
    return int(lib.mk_plan_add_node(k,node_id,kind,None,0,resource))

def scenario(lib):
    z=Time(); assert lib.mk_time_add(Time(1001,30000),Time(1,48000),ctypes.byref(z))==MK_OK
    assert (z.num,z.den)==(2671,80000)
    k=lib.mk_kernel_create(); assert k
    try:
        assert lib.mk_kernel_add_asset(k,b"a.mp4",Time(10,1))==MK_OK
        assert lib.mk_kernel_add_asset(k,b"b.mp4",Time(8,1))==MK_OK
        assert lib.mk_kernel_add_asset(k,b"a.mp4",Time(10,1))==MK_CONFLICT
        assert lib.mk_kernel_append_clip(k,b"a.mp4",Time(0,1),Time(6,1),Time(0,1))==MK_OK
        assert lib.mk_kernel_append_clip(k,b"b.mp4",Time(0,1),Time(5,1),Time(1,2))==MK_OK
        assert lib.mk_kernel_append_clip(k,b"missing.mp4",Time(0,1),Time(1,1),Time(0,1))==MK_NOT_FOUND
        assert lib.mk_kernel_append_clip(k,b"b.mp4",Time(7,1),Time(5,1),Time(0,1))==MK_INVALID
        before=int(lib.mk_kernel_state_hash(k)); p=ctypes.c_uint64()
        assert lib.mk_kernel_propose_trim(k,0,0,Time(5,1),ctypes.byref(p))==MK_OK
        assert int(lib.mk_kernel_state_hash(k))==before and lib.mk_kernel_revision(k)==0
        rev=ctypes.c_uint64(); assert lib.mk_kernel_commit(k,p.value,ctypes.byref(rev))==MK_OK and rev.value==1
        stale=ctypes.c_uint64(); assert lib.mk_kernel_propose_trim(k,0,0,Time(4,1),ctypes.byref(stale))==MK_CONFLICT
        a,b=Handle(),Handle(); assert lib.mk_resource_alloc(k,4096,1,ctypes.byref(a))==MK_OK; assert lib.mk_resource_alloc(k,8192,2,ctypes.byref(b))==MK_OK
        rc=ctypes.c_uint32(); assert lib.mk_resource_refcount(k,a,ctypes.byref(rc))==MK_OK and rc.value==1
        assert lib.mk_resource_retain(k,a)==MK_OK; assert lib.mk_resource_release(k,a)==MK_OK; assert lib.mk_resource_release(k,a)==MK_OK
        assert lib.mk_resource_touch(k,a)==MK_STALE and lib.mk_resource_release(k,a)==MK_STALE
        c=Handle(); assert lib.mk_resource_alloc(k,16384,3,ctypes.byref(c))==MK_OK
        assert c.slot==a.slot and c.generation!=a.generation
        assert lib.mk_plan_reset(k)==MK_OK
        assert add_node(lib,k,10,SRC,[],b)==MK_OK and add_node(lib,k,20,XFORM,[10],c)==MK_OK and add_node(lib,k,30,SINK,[20])==MK_OK
        assert lib.mk_plan_validate(k)==MK_OK; good_hash=int(lib.mk_plan_hash(k))
        assert add_node(lib,k,30,SINK,[20])==MK_CONFLICT
        assert lib.mk_plan_reset(k)==MK_OK; assert add_node(lib,k,1,XFORM,[2])==MK_OK; assert add_node(lib,k,2,XFORM,[1])==MK_OK; assert lib.mk_plan_validate(k)==MK_CYCLE
        assert lib.mk_plan_reset(k)==MK_OK; assert add_node(lib,k,1,SRC,[])==MK_OK; assert add_node(lib,k,2,SINK,[999])==MK_OK; assert lib.mk_plan_validate(k)==MK_INVALID
        assert lib.mk_plan_reset(k)==MK_OK; assert add_node(lib,k,1,SRC,[],a)==MK_OK; assert add_node(lib,k,2,SINK,[1])==MK_OK; assert lib.mk_plan_validate(k)==MK_STALE
        assert lib.mk_plan_reset(k)==MK_OK; assert add_node(lib,k,10,SRC,[],b)==MK_OK; assert add_node(lib,k,20,XFORM,[10],c)==MK_OK; assert add_node(lib,k,30,SINK,[20])==MK_OK; assert lib.mk_plan_validate(k)==MK_OK
        return {"time":[z.num,z.den],"revision":int(lib.mk_kernel_revision(k)),"state_hash":int(lib.mk_kernel_state_hash(k)),"resource_hash":int(lib.mk_resource_hash(k)),"plan_hash":int(lib.mk_plan_hash(k)),"good_plan_hash":good_hash,"reuse":[c.slot,c.generation],"ffmpeg":int(lib.mk_ffmpeg_version())}
    finally: lib.mk_kernel_destroy(k)

def dput(d,*vals):
    for v in vals: d.update(int(v).to_bytes(8,"little",signed=False))

def resource_stress(lib,ops=30000,seed=0xD3C11F):
    rng=random.Random(seed); k=lib.mk_kernel_create(); assert k; tokens=[]; d=hashlib.sha256(); start=time.perf_counter()
    try:
        for step in range(ops):
            active=sum(t[2] for t in tokens)
            if not tokens or (rng.random()<0.24 and active<96):
                h=Handle(); size=512*(1+rng.randrange(64)); domain=1+rng.randrange(4); st=int(lib.mk_resource_alloc(k,size,domain,ctypes.byref(h))); dput(d,step,st,h.slot,h.generation)
                if st==MK_OK: tokens.append([Handle(h.slot,h.generation),1,True])
                continue
            idx=rng.randrange(len(tokens)); h,refs,is_active=tokens[idx]; choice=rng.random()
            if choice<0.22:
                st=int(lib.mk_resource_retain(k,h)); expected=MK_OK if is_active else MK_STALE
                if st==MK_OK: tokens[idx][1]+=1
            elif choice<0.72:
                st=int(lib.mk_resource_release(k,h)); expected=MK_OK if is_active else MK_STALE
                if st==MK_OK:
                    tokens[idx][1]-=1
                    if tokens[idx][1]==0: tokens[idx][2]=False
            elif choice<0.92:
                st=int(lib.mk_resource_touch(k,h)); expected=MK_OK if is_active else MK_STALE
            else:
                out=ctypes.c_uint32(0xDEADBEEF); st=int(lib.mk_resource_refcount(k,h,ctypes.byref(out))); expected=MK_OK if is_active else MK_STALE
                if st==MK_OK: assert out.value==refs
                dput(d,out.value)
            assert st==expected,(step,choice,st,expected,idx,refs,is_active)
            dput(d,step,idx,st)
        return {"ops":ops,"seconds":time.perf_counter()-start,"digest":d.hexdigest(),"hash":int(lib.mk_resource_hash(k)),"tokens":len(tokens),"active":sum(t[2] for t in tokens)}
    finally: lib.mk_kernel_destroy(k)

def plan_stress(lib,cases=1200,seed=0xA11DA6):
    rng=random.Random(seed); k=lib.mk_kernel_create(); assert k; d=hashlib.sha256(); start=time.perf_counter()
    try:
        for case in range(cases):
            assert lib.mk_plan_reset(k)==MK_OK; mode=case%4
            if mode==0:
                count=5+rng.randrange(8); assert add_node(lib,k,1,SRC,[])==MK_OK
                for nid in range(2,count):
                    dep=1+rng.randrange(nid-1); deps=[dep]
                    if nid>3 and rng.random()<0.35:
                        dep2=1+rng.randrange(nid-1)
                        if dep2!=dep: deps.append(dep2)
                    assert add_node(lib,k,nid,XFORM,deps)==MK_OK
                assert add_node(lib,k,count,SINK,[count-1])==MK_OK; st=int(lib.mk_plan_validate(k)); assert st==MK_OK; dput(d,case,st,lib.mk_plan_hash(k))
            elif mode==1:
                assert add_node(lib,k,1,SRC,[])==MK_OK and add_node(lib,k,2,SINK,[999])==MK_OK; st=int(lib.mk_plan_validate(k)); assert st==MK_INVALID; dput(d,case,st)
            elif mode==2:
                assert add_node(lib,k,11,XFORM,[12])==MK_OK and add_node(lib,k,12,XFORM,[11])==MK_OK; st=int(lib.mk_plan_validate(k)); assert st==MK_CYCLE; dput(d,case,st)
            else:
                h=Handle(); assert lib.mk_resource_alloc(k,1024,1,ctypes.byref(h))==MK_OK; assert lib.mk_resource_release(k,h)==MK_OK
                assert add_node(lib,k,1,SRC,[],h)==MK_OK and add_node(lib,k,2,SINK,[1])==MK_OK; st=int(lib.mk_plan_validate(k)); assert st==MK_STALE; dput(d,case,st,h.slot,h.generation)
        return {"cases":cases,"seconds":time.perf_counter()-start,"digest":d.hexdigest(),"resource_hash":int(lib.mk_resource_hash(k))}
    finally: lib.mk_kernel_destroy(k)

def bench(lib,iters,rounds):
    times=[]; sums=[]
    for _ in range(rounds):
        s=time.perf_counter(); sums.append(int(lib.mk_benchmark(iters))); times.append(time.perf_counter()-s)
    assert len(set(sums))==1
    return {"median":statistics.median(times),"min":min(times),"max":max(times),"checksum":sums[0]}

def read_time(name,warm=False):
    suffix="_WARM_BUILD_TIME" if warm else "_BUILD_TIME"; p=os.environ.get(f"MK_{name.upper()}{suffix}","")
    try: return float(Path(p).read_text().strip())
    except Exception: return None

def metrics(path,lang):
    text=Path(path).read_text(); m={"bytes":len(text.encode()),"loc":sum(bool(x.strip()) for x in text.splitlines())}
    if lang=="cpp": m|={"manual_memory":text.count("new mk_kernel")+text.count("delete kernel"),"pointer_markers":text.count("*")}
    if lang=="rust": m|={"manual_memory":text.count("Box::into_raw")+text.count("Box::from_raw"),"unsafe":text.count("unsafe"),"raw_pointer_tokens":text.count("*mut ")+text.count("*const ")}
    if lang=="zig": m|={"manual_memory":text.count("c.malloc")+text.count("c.free"),"pointer_casts":text.count("@ptrCast")+text.count("@alignCast")}
    if lang=="odin": m|={"manual_memory":text.count("new(Kernel)")+text.count("free("),"rawptr":text.count("rawptr"),"pointer_casts":text.count("cast(^Kernel)"),"ffi_context":text.count("runtime.default_context()")}
    return m

def main():
    if len(sys.argv)!=5: raise SystemExit("runner.py CPP RUST ZIG ODIN")
    names=["cpp","rust","zig","odin"]; paths=dict(zip(names,map(Path,sys.argv[1:])))
    src={"cpp":ROOT/"cpp/kernel.cpp","rust":ROOT/"rust/src/lib.rs","zig":ROOT/"zig/kernel.zig","odin":ROOT/"odin/kernel.odin"}
    iters=int(os.getenv("MK_BENCH_ITERATIONS","5000000")); rounds=int(os.getenv("MK_BENCH_ROUNDS","5")); rops=int(os.getenv("MK_RESOURCE_STRESS_OPS","30000")); pcases=int(os.getenv("MK_PLAN_STRESS_CASES","1200"))
    results={}
    for name in names:
        lib=load(paths[name]); results[name]={"scenario":scenario(lib),"resource":resource_stress(lib,rops),"plan":plan_stress(lib,pcases),"benchmark":bench(lib,iters,rounds),"binary":paths[name].stat().st_size,"cold":read_time(name),"warm":read_time(name,True),"source":metrics(src[name],name)}
    checks=[("scenario",k) for k in ("time","revision","state_hash","resource_hash","plan_hash","good_plan_hash","reuse","ffmpeg")]+[("resource",k) for k in ("digest","hash","tokens","active")]+[("plan",k) for k in ("digest","resource_hash")]+[("benchmark","checksum")]
    eq={f"{s}.{k}":len({json.dumps(results[n][s][k],sort_keys=True) for n in names})==1 for s,k in checks}; assert all(eq.values()),[k for k,v in eq.items() if not v]
    payload={"equivalence":eq,"results":results,"notes":{"scope":"revisioned state, candidate commits, generational resources, typed DAG validation, deterministic hashes, C ABI, libavformat","failure":"randomized stale-handle and invalid-DAG behavior; not a proof of memory or concurrency safety","storage":"fixed-capacity stores in all four languages","performance":"sanity/overhead probes, not rendering throughput"}}
    Path("architecture-bakeoff-results.json").write_text(json.dumps(payload,indent=2)+"\n")
    print(json.dumps(payload,indent=2))

if __name__=="__main__": main()
