"""Gauge a Manin relation graph and retain only independent dual coordinates."""
from pathlib import Path
import sys,json,hashlib,time
G,P,C,O=map(Path,sys.argv[1:]);tt=time.monotonic();cert=json.loads(C.read_text())
with G.open()as f:
 q,p,n,ns,nr,nnz,c2,ei,ec=map(int,next(f).split());cols=[[]for _ in range(ns)]
 for r in range(nr):
  a=list(map(int,next(f).split()))
  for j,v in zip(a[1::2],a[2::2]):cols[j].append((r,v))
 R=[]
 for i in range(ns):
  a=list(map(int,next(f).split()));R.append(list(zip(a[1::2],a[2::2])))
 assert not f.read().strip()
with P.open()as f:
 qq,nn,k,zz=map(int,next(f).split());v=list(map(int,next(f).split()));u=list(map(int,next(f).split()));assert(qq,nn,zz)==(q,ns,nnz)
 for i in range(ns):next(f)
 checks=list(map(int,next(f).split()));assert checks[0]==64
nodes=cert['nodes'];par=[a[0]for a in nodes];edge=[a[1]for a in nodes];comp=[a[2]for a in nodes];pivot=[a[4]for a in nodes];roots=[r for r in range(nr+1)if par[r]==r];children=[[]for _ in nodes]
for r in range(nr):
 if par[r]!=r:children[par[r]].append(r)
mu=[0]*(nr+1);order=[];todo=roots[:]
while todo:
 r=todo.pop();order.append(r)
 if par[r]==r:mu[r]=1
 else:
  a=dict(cols[edge[r]])[r];b=1 if par[r]==nr else dict(cols[edge[r]])[par[r]];mu[r]=-mu[par[r]]*b*pow(a,-1,q)%q
 todo.extend(children[r])
assert len(order)==nr+1 and all(mu)
tree={edge[r]for r in range(nr)if par[r]!=r};pivots={pivot[r]for r in roots if pivot[r]>=0};excluded=tree|pivots;free=[j for j in range(ns)if j not in excluded];assert len(free)==k+2
scale=[1]*ns
for r in range(nr):
 if par[r]!=r:scale[edge[r]]=mu[r]*dict(cols[edge[r]])[r]%q
for j in range(ns):
 if j not in tree and cols[j]:scale[j]=mu[cols[j][0][0]]*cols[j][0][1]%q
assert all(scale);invscale=[pow(a,-1,q)for a in scale]
def column(j):
 cc=cols[j]
 if not cc:return(nr,nr,0,nr)
 r,a=cc[0];s,b=cc[1]if len(cc)==2 else(nr,0);rho=mu[s]*b*invscale[j]%q if s!=nr else 0
 assert mu[r]*a*invscale[j]%q==1
 return(r,s,rho,comp[r])
freecols=[column(j)for j in free];pv=[]
for root in roots:
 if pivot[root]>=0:
  j=pivot[root];r,s,rho,cr=column(j);assert cr==root and s!=nr and(1+rho)%q;pv.append((root,j,r,s,rho,pow(1+rho,-1,q)))
tr=[(r,par[r],edge[r])for r in reversed(order)if par[r]!=r];unanch=[r for r in roots if r!=nr]
w0=[a*b%q for a,b in zip(scale,u)];wind=[(j,v[j]*invscale[j]%q)for j in range(ns)if v[j]];RR=[[(j,a*scale[i]*invscale[j]%q)for j,a in R[i]]for i in free]
def reconstruct(vals):
 w=[0]*ns;b=[0]*nr;res=[0]*(nr+1)
 for j,x,(r,s,rho,root)in zip(free,vals,freecols):
  w[j]=x
  if r==nr:continue
  b[r]=(b[r]+x)%q
  if s!=nr:b[s]=(b[s]+rho*x)%q
  if root!=nr:res[root]=(res[root]+x+(rho*x if s!=nr else 0))%q
 for root,j,r,s,rho,iv in pv:
  x=-res[root]*iv%q;w[j]=x;b[r]=(b[r]+x)%q;b[s]=(b[s]+rho*x)%q
 for r,pr,j in tr:
  w[j]=-b[r]%q
  if pr!=nr:b[pr]=(b[pr]+b[r])%q
 assert all(b[r]==0 for r in unanch)
 return w
assert reconstruct([w0[j]for j in free])==w0
new=reconstruct([sum(a*w0[j]for j,a in row)%q for row in RR]);expected=[scale[i]*sum(a*u[j]for j,a in R[i])%q for i in range(ns)];assert new==expected
with O.open('w')as f:
 f.write(f'{q} {p} {n} {ns} {k} {nr} {len(free)} {len(wind)} {len(tr)} {len(pv)} {len(unanch)}\n')
 for row in [mu[:nr],scale,w0,checks[1:],free]:f.write(' '.join(map(str,row))+'\n')
 for j,a in wind:f.write(f'{j} {a}\n')
 for row in RR:f.write(str(len(row))+' '+' '.join(f'{j} {a}'for j,a in row)+'\n')
 for row in freecols+pv+tr:f.write(' '.join(map(str,row))+'\n')
 f.write(' '.join(map(str,unanch))+'\n')
print('S21_FREE_GRAPH_PREPARED',p,n,'ambient',ns,'free',len(free),'seconds',round(time.monotonic()-tt,2),flush=True)
