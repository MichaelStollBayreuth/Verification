"""Linear-size exact rank, kernel functional and winding-vector certificates.

Lower rank: tree columns have leaf pivots; one nonzero reduced chord adds
the root pivot in each unbalanced component. Upper rank: disjoint-support
left-null vectors from every balanced component. This checks both bounds.
"""
from pathlib import Path
import sys,json,hashlib,gzip
def sha(p):
 return hashlib.sha256(p.read_bytes()).hexdigest()  # (hashlib.file_digest needs Python 3.11)
def op(p):return gzip.open(p,'rt')if p.suffix=='.gz'else p.open()
graph,prepared,certificate,out=map(Path,sys.argv[1:]);data=json.loads(certificate.read_text());assert data['status']=='PASS'
with op(graph)as f:
 q,p,n,ns,nr,nnz,c2,ei,ec=map(int,next(f).split());assert 0<=ei<ns and 0<ec<q and 0<c2<q
 rows=[];cols=[[]for j in range(ns)]
 for r in range(nr):
  a=list(map(int,next(f).split()));z=a[0];assert len(a)==2*z+1 and 1<=z<=3;rr=list(zip(a[1::2],a[2::2]));assert sorted(set(c for c,v in rr))==[c for c,v in rr]
  for c,v in rr:assert 0<=c<ns and 0<v<q;cols[c].append((r,v))
  rows.append(rr)
 R=[]
 for j in range(ns):
  a=list(map(int,next(f).split()));assert len(a)==2*a[0]+1;rr=list(zip(a[1::2],a[2::2]));assert sorted(set(c for c,v in rr))==[c for c,v in rr]
  for c,v in rr:assert 0<=c<ns and 0<v<q
  R.append(rr)
 assert not f.read().strip()
assert all(len(c)<=2 for c in cols)and sum(map(len,R))==nnz
nodes=data['nodes'];assert len(nodes)==nr+1;dummy=nr
parent=[r[0]for r in nodes];edge=[r[1]for r in nodes];comp=[r[2]for r in nodes];lam=[r[3]for r in nodes];pivot=[r[4]for r in nodes]
roots=[r for r in range(nr+1)if parent[r]==r];assert dummy in roots;children=[[]for r in nodes];tree=set()
for r in range(nr+1):
 assert 0<=parent[r]<=nr and 0<=comp[r]<=nr and 0<=lam[r]<q
 if r in roots:assert comp[r]==r
 else:
  assert edge[r]not in tree;tree.add(edge[r]);assert 0<=edge[r]<ns
  actual={v for v,a in cols[edge[r]]};expected={r,parent[r]}-{dummy};assert actual==expected
  if len(cols[edge[r]])==1:assert dummy in [r,parent[r]]
  children[parent[r]].append(r)
visited=[];todo=roots[:]
while todo:
 r=todo.pop();visited.append(r)
 for s in children[r]:assert comp[s]==comp[r];todo.append(s)
assert sorted(visited)==list(range(nr+1))
balanced=[];extra=[]
for r in roots:
 if r==dummy:assert lam[r]==0 and pivot[r]==-1
 else:
  assert lam[r]==1
  if pivot[r]<0:balanced.append(r)
  else:assert pivot[r]not in tree and 0<=pivot[r]<ns;extra.append(pivot[r])
for r in range(nr):assert (lam[r]==0)==(comp[r]==dummy)
assert len(set(extra))==len(extra)
reduced=[]
for c,cc in enumerate(cols):
 if not cc:reduced.append(0);continue
 root=comp[cc[0][0]];assert all(comp[r]==root for r,v in cc)
 v=sum(lam[r]*a for r,a in cc)%q;reduced.append(v)
 if c in tree or root in balanced:assert v==0
for root in roots:
 if pivot[root]>=0:assert reduced[pivot[root]]!=0 and all(comp[r]==root for r,a in cols[pivot[root]])
rank=len(tree)+len(extra);assert rank==nr-len(balanced)==data['relation_rank']and data['balanced_components']==len(balanced)
assert data['p']==p and data['order']==n and data['q']==q and data['generators']==ns and data['relations']==nr and data['dimension']==ns-rank and data['cuspidal_dimension']==ns-rank-2
with op(prepared)as f:
 qq,nn,k,zz=map(int,next(f).split());assert(qq,nn,zz)==(q,ns,nnz)and k==data['cuspidal_dimension'];v=list(map(int,next(f).split()));u=list(map(int,next(f).split()));assert len(v)==len(u)==ns and all(0<=a<q for a in v+u)
 for rr in R:
  a=list(map(int,next(f).split()));assert a[0]==len(rr)and list(zip(a[1::2],a[2::2]))==rr
 checks=list(map(int,next(f).split()));assert len(checks)==65 and checks[0]==64 and all(0<=a<q for a in checks[1:]);assert not f.read().strip()
for rr in rows:assert sum(a*u[c]for c,a in rr)%q==0
# The two Eisenstein factors are checked directly on the raw identity symbol.
def act_sparse(v):
 d={}
 for i,a in v.items():
  for j,b in R[i]:d[j]=(d.get(j,0)+a*b)%q
 return {j:a for j,a in d.items()if a}
e={ei:ec}
for a in [(2*c2+1)%q,(c2+2)%q]:
 d=act_sparse(e)
 for j,b in e.items():d[j]=(d.get(j,0)-a*b)%q
 e={j:b for j,b in d.items()if b}
assert {j:a for j,a in enumerate(v)if a}==e
result={'status':'PASS','p':p,'order':n,'q':q,'generators':ns,'relation_rank':rank,'full_dimension':ns-rank,'cuspidal_dimension':k,'all_functional_relations_verified':True,'rank_lower_and_upper_certificates_verified':True,'winding_vector_verified':True,'all_prepared_operator_rows_identical':True,'graph_sha256':sha(graph),'prepared_sha256':sha(prepared),'rank_certificate_sha256':sha(certificate),'verifier_sha256':sha(Path(__file__))}
out.write_text(json.dumps(result,indent=2)+'\n');print('S20_GRAPH_INDEPENDENT_CERTIFICATE_PASS',p,n,'rank',rank,'cuspidal_dimension',k,flush=True)
