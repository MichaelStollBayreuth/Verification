#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <vector>
#include <ctime>
using namespace std;
struct Entry{uint32_t j,a;};struct Column{uint32_t r,s,rho,root;};struct Pivot{uint32_t root,j,r,s,rho,iv;};struct Tree{uint32_t r,p,j;};
int main(int argc,char**argv){
 assert(argc==3);clock_t started=clock();ifstream in(argv[1]);assert(in);uint64_t q;size_t p,ord,n,k,nr,nf,ne,nt,np,nroot;in>>q>>p>>ord>>n>>k>>nr>>nf>>ne>>nt>>np>>nroot;assert(q>3&&q<=UINT32_MAX&&n<UINT32_MAX&&nf==k+2&&nf+nt+np==n);
 vector<uint32_t>mu(nr),scale(n),w(n),check(64),free(nf);for(auto&x:mu){in>>x;assert(x&&x<q);}for(auto&x:scale){in>>x;assert(x&&x<q);}for(auto&x:w){in>>x;assert(x<q);}for(auto&x:check){in>>x;assert(x<q);}for(auto&x:free){in>>x;assert(x<n);}
 vector<Entry>wind(ne);for(auto&e:wind){in>>e.j>>e.a;assert(e.j<n&&e.a&&e.a<q);}vector<vector<Entry>>R(nf);size_t maxrow=0,nnz=0;
 for(auto&row:R){size_t z;in>>z;assert(z<=n);maxrow=max(maxrow,z);nnz+=z;row.resize(z);for(auto&e:row){in>>e.j>>e.a;assert(e.j<n&&e.a&&e.a<q);}}
 vector<Column>cols(nf);for(auto&c:cols){in>>c.r>>c.s>>c.rho>>c.root;assert(c.r<=nr&&c.s<=nr&&c.rho<q&&c.root<=nr);}vector<Pivot>pivs(np);for(auto&a:pivs){in>>a.root>>a.j>>a.r>>a.s>>a.rho>>a.iv;assert(a.root<nr&&a.j<n&&a.r<nr&&a.s<nr&&a.rho<q&&a.iv<q&&((uint64_t(1)+a.rho)*a.iv)%q==1);}
 vector<Tree>tree(nt);for(auto&a:tree){in>>a.r>>a.p>>a.j;assert(a.r<nr&&a.p<=nr&&a.j<n);}vector<uint32_t>roots(nroot);for(auto&r:roots){in>>r;assert(r<nr);}assert(in);string extra;assert(!(in>>extra));
 const uint64_t reciprocal=uint64_t(((__uint128_t)1<<64)/q);
 auto reduce=[&](uint64_t z)->uint32_t{uint64_t h=uint64_t(((__uint128_t)z*reciprocal)>>64);uint64_t r=z-h*q;return r>=q?r-q:r;};
 auto add=[&](uint32_t a,uint32_t b)->uint32_t{uint64_t z=uint64_t(a)+b;return z>=q?z-q:z;};auto neg=[&](uint32_t a)->uint32_t{return a?q-a:0;};auto mul=[&](uint32_t a,uint32_t b)->uint32_t{return reduce(uint64_t(a)*b);};
 bool safe_rows=maxrow*((__uint128_t)(q-1)*(q-1))<=UINT64_MAX,safe_wind=ne*((__uint128_t)(q-1)*(q-1))<=UINT64_MAX;vector<uint32_t>values(nf),b(nr),res(nr+1);
 vector<array<Entry,4>> packed; if(maxrow<=4){packed.resize(nf);for(size_t i=0;i<nf;i++)for(size_t j=0;j<4;j++)packed[i][j]=j<R[i].size()?R[i][j]:Entry{0,0};R.clear();R.shrink_to_fit();}
 ofstream out(argv[2]);assert(out);out<<"q:="<<q<<";dimension:="<<k<<";sequence:=[";
 for(size_t step=0;step<2*k;step++){
  uint32_t scalar;
  if(safe_wind){uint64_t z=0;for(auto&e:wind)z+=uint64_t(w[e.j])*e.a;scalar=reduce(z);}else{__uint128_t z=0;for(auto&e:wind)z+=(__uint128_t)w[e.j]*e.a;scalar=z%q;}
  if(step<64)assert(scalar==check[step]);if(step)out<<',';out<<scalar;
  for(size_t i=0;i<nf;i++){
   if(safe_rows&&!packed.empty()){auto&v=packed[i];uint64_t z=uint64_t(w[v[0].j])*v[0].a+uint64_t(w[v[1].j])*v[1].a+uint64_t(w[v[2].j])*v[2].a+uint64_t(w[v[3].j])*v[3].a;values[i]=reduce(z);}
   else if(safe_rows){uint64_t z=0;for(auto&e:R[i])z+=uint64_t(w[e.j])*e.a;values[i]=reduce(z);}else{__uint128_t z=0;if(!packed.empty()){for(auto&e:packed[i])z+=(__uint128_t)w[e.j]*e.a;}else{for(auto&e:R[i])z+=(__uint128_t)w[e.j]*e.a;}values[i]=z%q;}
  }
  fill(b.begin(),b.end(),0);fill(res.begin(),res.end(),0);
  for(size_t i=0;i<nf;i++){auto x=values[i];w[free[i]]=x;auto&c=cols[i];if(c.r==nr)continue;b[c.r]=add(b[c.r],x);uint32_t y=0;if(c.s!=nr){y=mul(c.rho,x);b[c.s]=add(b[c.s],y);}if(c.root!=nr)res[c.root]=add(res[c.root],add(x,y));}
  for(auto&a:pivs){auto x=mul(neg(res[a.root]),a.iv);w[a.j]=x;b[a.r]=add(b[a.r],x);b[a.s]=add(b[a.s],mul(a.rho,x));}
  for(auto&a:tree){w[a.j]=neg(b[a.r]);if(a.p!=nr)b[a.p]=add(b[a.p],b[a.r]);}
  for(auto r:roots)assert(b[r]==0);
 }
 out<<"];\n";out.close();cout<<"S22_PACKED_GRAPH_KRYLOV_COMPLETE p="<<p<<" order="<<ord<<" q="<<q<<" ambient_dimension="<<n<<" dimension="<<k<<" free_dimension="<<nf<<" free_nnz="<<nnz<<" native_prefix_checked=64 cpu_seconds="<<double(clock()-started)/CLOCKS_PER_SEC<<endl;
}
