# Point search with ratpoints-3.1.1 on the failure curves of the Sto19 tables (curves.txt from mklist.py).
# Usage: python3 run.py H JOBS OUT [CURVES]. One line per curve: g, i, h, H, number and list of the
# extra x (x != 0 finite), seconds. Appends to OUT and skips the curves already there (resumable).
import sys, os, subprocess, time
from multiprocessing import Pool
H, J, OUT = sys.argv[1], int(sys.argv[2]), sys.argv[3]
def work(line):
    g, i, h, a = line.rstrip('\n').split('\t')
    t = time.time()
    out = subprocess.run(['ratpoints', a, H, '-q', '-t', '1'], capture_output=True, text=True, check=True).stdout
    xs = []
    for l in out.split('\n'):
        if l.startswith('('):
            u, v, w = (int(s) for s in l.strip('()').split(':'))
            if w != 0 and u != 0 and v >= 0: xs.append('%d/%d' % (u, w) if w != 1 else str(u))
    return '%s\t%s\t%s\t%s\t%d\t%s\t%.3f\n' % (g, i, h, H, len(xs), ','.join(xs), time.time() - t)
if __name__ == '__main__':
    done = set()
    if os.path.exists(OUT):
        done = {tuple(l.split('\t')[:2]) for l in open(OUT) if l.count('\t') == 6 and l.endswith('\n')}
    lines = [l for l in open(sys.argv[4] if len(sys.argv) > 4 else 'curves.txt')
             if tuple(l.split('\t')[:2]) not in done]
    with open(OUT, 'a') as f, Pool(J) as p:
        for r in p.imap_unordered(work, lines, chunksize=4):
            f.write(r)
            f.flush()
