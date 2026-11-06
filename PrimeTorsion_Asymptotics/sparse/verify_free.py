"""Independent complete coefficient check for a dual-coordinate Manin plan."""
from pathlib import Path
import sys,json,hashlib
G,P,C,V,L,O=map(Path,sys.argv[1:])
def sha(p):
 return hashlib.sha256(p.read_bytes()).hexdigest()  # (hashlib.file_digest needs Python 3.11)
vc=json.loads(V.read_text());cert=json.loads(C.read_text());assert vc['status']==cert['status']=='PASS';assert vc['graph_sha256']==sha(G)and vc['prepared_sha256']==sha(P)and vc['rank_certificate_sha256']==sha(C)
with G.open()as f:
 q,p,n,ns,nr,nnz,c2,ei,ec=map(int,next(f).split());cols=[[]for _ in range(ns)];A=[]
 for r in range(nr):
  aa=list(map(int,next(f).split()));row=list(zip(aa[1::2],aa[2::2]));A.append(row)
  for j,a in row:cols[j].append((r,a))
 R=[]
 for _ in range(ns):
  aa=list(map(int,next(f).split()));R.append(list(zip(aa[1::2],aa[2::2])))
 assert not f.read().strip()
with P.open()as f:
 qq,nn,k,zz=map(int,next(f).split());v=list(map(int,next(f).split()));u=list(map(int,next(f).split()));assert(qq,nn,zz)==(q,ns,nnz)
 for _ in range(ns):next(f)
 expected_checks=list(map(int,next(f).split()));assert expected_checks[0]==64
with L.open()as f:
 hh=list(map(int,next(f).split()));assert hh[:6]==[q,p,n,ns,k,nr];nf,ne,nt,np,nroot=hh[6:];assert nf==k+2 and nf+nt+np==ns
 mu,scale,w,checks,free=[list(map(int,next(f).split()))for _ in range(5)];assert[len(mu),len(scale),len(w),len(checks),len(free)]==[nr,ns,ns,64,nf]
 wind=[tuple(map(int,next(f).split()))for _ in range(ne)];RR=[]
 for _ in range(nf):
  aa=list(map(int,next(f).split()));assert len(aa)==1+2*aa[0];RR.append(list(zip(aa[1::2],aa[2::2])))
 fc=[tuple(map(int,next(f).split()))for _ in range(nf)];pv=[tuple(map(int,next(f).split()))for _ in range(np)];tr=[tuple(map(int,next(f).split()))for _ in range(nt)];roots=list(map(int,next(f).split()));assert len(roots)==nroot and not f.read().strip()
assert checks==expected_checks[1:]and all(0<a<q for a in mu+scale)and all(0<=a<q for a in w)
assert w==[a*b%q for a,b in zip(scale,u)];iv=[pow(a,-1,q)for a in scale];assert wind==[(j,a*iv[j]%q)for j,a in enumerate(v)if a]
nodes=cert['nodes'];par=[r[0]for r in nodes];edge=[r[1]for r in nodes];comp=[r[2]for r in nodes];piv=[r[4]for r in nodes];allroots=[r for r in range(nr+1)if par[r]==r];assert roots==[r for r in allroots if r!=nr]
tree={edge[r]:r for r in range(nr)if par[r]!=r};pc={piv[r]:r for r in allroots if piv[r]>=0};excluded=set(tree)|set(pc);assert free==[j for j in range(ns)if j not in excluded]and len(free)==nf and ns-nf==vc['relation_rank'];assert len(tr)==len(tree)
assert sorted(tr)==sorted((r,par[r],edge[r])for r in range(nr)if par[r]!=r)
positions={r:i for i,(r,pr,j)in enumerate(tr)}
for r,pr,j in tr:
 assert pr==nr or pr not in positions or positions[r]<positions[pr]
 assert {a for a,b in cols[j]}=={r,pr}-{nr}
 assert all(mu[a]*b*iv[j]%q==(1 if a==r else q-1)for a,b in cols[j])
for i,row in zip(free,RR):assert row==[(j,a*scale[i]*iv[j]%q)for j,a in R[i]]
for j,(r,s,rho,root)in zip(free,fc):
 cc=cols[j]
 if not cc:assert(r,s,rho,root)==(nr,nr,0,nr)
 else:
  assert cc[0][0]==r and mu[r]*cc[0][1]*iv[j]%q==1 and root==comp[r]
  if len(cc)==1:assert s==root==nr and rho==0
  else:assert cc[1][0]==s and comp[s]==root and rho==mu[s]*cc[1][1]*iv[j]%q
assert {a[1]for a in pv}==set(pc)and len(pv)==len(pc)
for root,j,r,s,rho,invg in pv:
 assert pc[j]==root==comp[r]==comp[s]and root!=nr and cols[j][0][0]==r and cols[j][1][0]==s and mu[r]*cols[j][0][1]*iv[j]%q==1 and mu[s]*cols[j][1][1]*iv[j]%q==rho and(1+rho)*invg%q==1
# Reconstruct a kernel vector using separately written exact integer arithmetic.
def rebuild(values):
 ww=[0]*ns;b=[0]*nr;total=[0]*(nr+1)
 for j,x,(r,s,rho,root)in zip(free,values,fc):
  ww[j]=x
  if r<nr:
   b[r]+=x
   if s<nr:b[s]+=rho*x
   if root<nr:total[root]+=x+(rho*x if s<nr else 0)
 for root,j,r,s,rho,invg in pv:
  x=(-total[root]*invg)%q;ww[j]=x;b[r]+=x;b[s]+=rho*x
 for r,pr,j in tr:
  ww[j]=(-b[r])%q
  if pr<nr:b[pr]+=b[r]
 assert all(b[r]%q==0 for r in roots)
 return ww
assert rebuild([w[j]for j in free])==w
new=rebuild([sum(a*w[j]for j,a in row)%q for row in RR]);assert new==[scale[i]*sum(a*u[j]for j,a in R[i])%q for i in range(ns)]
maxrow=max(map(len,RR),default=0)
out={'status':'PASS','p':p,'order':n,'q':q,'ambient_dimension':ns,'dimension':k,'free_dimension':nf,'all_gauged_incidence_coefficients_checked':True,'all_free_operator_entries_checked':True,'forest_order_and_pivots_checked':True,'initial_vector_and_winding_checked':True,'full_one_step_operator_match':True,'free_nnz':sum(map(len,RR)),'max_free_row':maxrow,'max_winding_terms':ne,'safe_uint64_free_rows':maxrow*(q-1)**2<=2**64-1,'safe_uint64_winding':ne*(q-1)**2<=2**64-1,'graph_sha256':sha(G),'prepared_sha256':sha(P),'rank_certificate_sha256':sha(C),'graph_verification_sha256':sha(V),'free_plan_sha256':sha(L),'verifier_sha256':sha(Path(__file__))}
O.write_text(json.dumps(out,indent=2)+'\n');print('S21_FREE_GRAPH_INDEPENDENT_PASS',p,n,'free',nf,flush=True)
