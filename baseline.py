"""Short, non-destructive observations. Never runs model inference automatically."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
from beldin.metrics import snapshot

root = Path(__file__).resolve().parent
data = snapshot(root)
start = time.perf_counter()
count = 0
while time.perf_counter()-start < .25:
    hashlib.sha256(b'x'*65536).digest(); count += 1
data['cpu_short_check'] = {'duration_seconds': time.perf_counter()-start, 'sha256_64k_iterations': count, 'interpretation': 'Single-thread responsiveness observation, not a CPU rating'}
d = data['disk']
data['disk_throughput'] = {'available': False, 'reason': 'free_space_not_verified'}
if d['available'] and d['data']['free_bytes'] > 1024**3:
    block = b'Beldin baseline\n' * 65536
    with tempfile.TemporaryFile(dir=root) as f:
        start=time.perf_counter(); f.write(block); f.flush()
        import os
        os.fsync(f.fileno()); write=time.perf_counter()-start
        f.seek(0); start=time.perf_counter(); actual=f.read(); read=time.perf_counter()-start
        assert actual == block
    data['disk_throughput']={'available':True,'bytes':len(block),'write_seconds':write,'read_seconds':read,'caveat':'Small cached file; not physical device throughput'}
data['limitations']=['CIM hardware, network and firewall queries denied by session', 'Surface client source/contract not located', 'GPU contention: inference gated on available VRAM', 'No original Beldin files modified; new dedicated project']
(root/'VALKYRIE_BASELINE.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
print(json.dumps(data, indent=2))
