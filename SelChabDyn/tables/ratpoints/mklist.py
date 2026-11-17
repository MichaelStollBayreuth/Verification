# The curves of the tables without extra points up to 10^4 whose verdict is not "success"
# (failure, failure (A3), undetermined), as input for run.py. Usage, from this directory:
#     python3 mklist.py > curves.txt
# One line per curve, tab-separated: genus g, index i, h (coefficients from the constant term up),
# and the coefficients of f = x^(2g+1) + h^2 from the constant term up, separated by spaces (the
# input format of ratpoints).
import glob, os

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'raw')


def poly(g, h):
    h = list(map(int, h.split(',')))
    a = [0] * (2 * g + 2)
    for i, x in enumerate(h):
        for j, y in enumerate(h):
            a[i + j] += x * y
    a[2 * g + 1] += 1
    return a


if __name__ == '__main__':
    for fn in sorted(glob.glob(os.path.join(RAW, 'g*.txt'))):
        for line in open(fn):
            if not line.startswith('REC'):
                continue
            d = dict(kv.split('=', 1) for kv in line.rstrip('\n').split('\t')[1:])
            if d['nxs'] == '0' and d['v'] in ('fail', 'A3fail', 'A4fail', 'undet'):
                f = ' '.join(map(str, poly(int(d['g']), d['h'])))
                print('%s\t%s\t%s\t%s' % (d['g'], d['i'], d['h'], f))
