// Najman, github.com/F-Najman/Sd, degree22/optimization/prepare_graph.cpp (MIT, see LICENSE-Najman).
// Changed (for crt_verify.py; the default behavior is unchanged): with STRANGE_SEED=s in the
// environment the random functional u depends on s, and with STRANGE_RANDOM_START set the start
// vector is random instead of {0, oo} (then e' is a random element of S: cyclicity of T_2), and
// STRANGE_EIS="c1 c2" gives the eigenvalues of the exported operator on the two Eisenstein series
// (default 1 + 2 chi(2), 2 + chi(2): the operator T_2).
#include <algorithm>
#include <cstdlib>
#include <cassert>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <vector>
using namespace std;
struct Term{uint32_t r,a;};
struct DSU{vector<uint32_t>p,s;DSU(size_t n):p(n),s(n,1){iota(p.begin(),p.end(),0);}uint32_t root(uint32_t a){while(a!=p[a]){p[a]=p[p[a]];a=p[a];}return a;}bool join(uint32_t a,uint32_t b){a=root(a);b=root(b);if(a==b)return false;if(s[a]<s[b])swap(a,b);p[b]=a;s[a]+=s[b];return true;}};
int main(int argc,char**argv){
 assert(argc==4||argc==5);ifstream in(argv[1]);assert(in);uint64_t q;size_t p,ord,ns,nr,nnz,chi2,eidx,ec;in>>q>>p>>ord>>ns>>nr>>nnz>>chi2>>eidx>>ec;assert(q>3&&q<=numeric_limits<uint32_t>::max()&&eidx<ns&&ec<q&&chi2<q);
 size_t block=numeric_limits<uint64_t>::max()/((__uint128_t)(q-1)*(q-1));assert(block>0);
 auto add=[&](uint64_t a,uint64_t b){return(a+b)%q;};auto mul=[&](uint64_t a,uint64_t b){return a*b%q;};
 auto pw=[&](uint64_t a,uint64_t b){uint64_t z=1;while(b){if(b&1)z=z*a%q;a=a*a%q;b>>=1;}return z;};auto inv=[&](uint64_t a){assert(a&&a<q);auto z=pw(a,q-2);assert(mul(a,z)==1);return z;};
 vector<vector<Term>>cols(ns);vector<vector<pair<uint32_t,uint32_t>>>rows(nr);
 for(size_t r=0;r<nr;r++){size_t z;in>>z;assert(z&&z<=3);uint32_t old=0;for(size_t j=0;j<z;j++){uint32_t c,a;in>>c>>a;assert(c<ns&&a&&a<q&&(j==0||c>old));old=c;cols[c].push_back({uint32_t(r),a});rows[r].push_back({c,a});}}
 for(auto&c:cols)assert(c.size()<=2);
 uint32_t dummy=nr;DSU ds(nr+1);vector<char>tree(ns,false);vector<vector<pair<uint32_t,uint32_t>>>adj(nr+1);size_t ntree=0;
 for(size_t c=0;c<ns;c++)if(cols[c].size()){
  auto a=cols[c][0].r,b=cols[c].size()==2?cols[c][1].r:dummy;
  if(ds.join(a,b)){tree[c]=true;ntree++;adj[a].push_back({b,c});adj[b].push_back({a,c});}
 }
 auto coef=[&](uint32_t c,uint32_t r)->uint64_t{for(auto t:cols[c])if(t.r==r)return t.a;assert(false);return 0;};
 vector<uint32_t>par(nr+1,UINT32_MAX),pe(nr+1,UINT32_MAX),component(nr+1,UINT32_MAX),order,roots;vector<uint64_t>lambda(nr+1,0);vector<char>anchor(nr+1,false);
 vector<uint32_t>rootlist{dummy};for(size_t r=0;r<nr;r++)rootlist.push_back(r);
 for(auto r:rootlist)if(par[r]==UINT32_MAX){roots.push_back(r);par[r]=r;component[r]=r;anchor[r]=(r==dummy);lambda[r]=(r==dummy?0:1);size_t start=order.size();order.push_back(r);
  for(size_t j=start;j<order.size();j++){auto v=order[j];for(auto [w,c]:adj[v])if(par[w]==UINT32_MAX){par[w]=v;pe[w]=c;component[w]=r;lambda[w]=(v==dummy?0:(q-mul(lambda[v],coef(c,v)))*inv(coef(c,w))%q);order.push_back(w);}}
 }
 assert(order.size()==nr+1);
 vector<int64_t>pivot(nr+1,-1);vector<uint64_t>gamma(ns,0);
 for(size_t c=0;c<ns;c++)if(!tree[c]&&!cols[c].empty()){
  auto r=component[cols[c][0].r];for(auto t:cols[c]){assert(component[t.r]==r);gamma[c]=add(gamma[c],mul(lambda[t.r],t.a));}
  if(!anchor[r]&&gamma[c]&&pivot[r]<0)pivot[r]=c;
 }
 size_t rank=ntree;for(auto r:roots)if(pivot[r]>=0)rank++;assert(rank<=nr&&ns>rank+2);size_t dim=ns-rank,k=dim-2;
 uint64_t seed_off=getenv("STRANGE_SEED")?strtoull(getenv("STRANGE_SEED"),nullptr,10):0;mt19937_64 rng(20261030ULL+p*1234567ULL+ord+seed_off*1000003ULL);vector<uint64_t>u(ns,0),b(nr,0);
 for(size_t c=0;c<ns;c++)if(!tree[c]&&(cols[c].empty()||pivot[component[cols[c][0].r]]!=int64_t(c)))u[c]=rng()%q;
 for(size_t r=0;r<nr;r++)for(auto [c,a]:rows[r])b[r]=add(b[r],mul(a,u[c]));
 vector<uint64_t>res(nr+1,0);for(size_t r=0;r<nr;r++)res[component[r]]=add(res[component[r]],mul(lambda[r],b[r]));
 for(auto r:roots)if(!anchor[r]){if(pivot[r]>=0){auto c=pivot[r];u[c]=mul((q-res[r])%q,inv(gamma[c]));for(auto t:cols[c])b[t.r]=add(b[t.r],mul(t.a,u[c]));}else assert(res[r]==0);}
 for(size_t j=order.size();j-->0;){auto v=order[j];if(v==dummy)continue;if(par[v]==v){assert(b[v]==0);continue;}auto c=pe[v];u[c]=mul((q-b[v])%q,inv(coef(c,v)));b[v]=add(b[v],mul(coef(c,v),u[c]));assert(b[v]==0);if(par[v]!=dummy)b[par[v]]=add(b[par[v]],mul(coef(c,par[v]),u[c]));}
 if(argc==5){ifstream ref(argv[4]);assert(ref);size_t rq,rn,rk,rz;ref>>rq>>rn>>rk>>rz;assert(rq==q&&rn==ns&&rk==k);uint64_t z;for(size_t j=0;j<ns;j++)ref>>z;for(auto&x:u){ref>>x;assert(x<q);}assert(ref);}
 for(size_t r=0;r<nr;r++){uint64_t a=0;for(auto [c,v]:rows[r])a=add(a,mul(v,u[c]));assert(a==0);}
 // Explicit upper-rank certificate: one disjoint-support left-null vector
 // for every unanchored balanced component. Tree pivots and one nonzero
 // reduced chord per unbalanced component give the matching lower rank.
 size_t balanced=0;for(auto r:roots)if(r!=dummy&&pivot[r]<0)balanced++;
 assert(rank==nr-balanced);
 for(size_t c=0;c<ns;c++){uint64_t z=0;for(auto t:cols[c]){auto r=component[t.r];if(r!=dummy&&pivot[r]<0)z=add(z,mul(lambda[t.r],t.a));}assert(z==0);}
 vector<size_t>off(ns+1,0);vector<uint32_t>sr(nnz),ci(nnz),va(nnz);size_t count=0;
 for(size_t i=0;i<ns;i++){size_t z;in>>z;assert(z<=ns);for(size_t j=0;j<z;j++){uint32_t c,a;in>>c>>a;assert(c<ns&&a&&a<q&&count<nnz);sr[count]=i;ci[count]=c;va[count]=a;off[c+1]++;count++;}}string extra;assert(in&&count==nnz&&!(in>>extra));partial_sum(off.begin(),off.end(),off.begin());auto pos=off;vector<uint32_t>src(nnz),a(nnz);for(size_t j=0;j<nnz;j++){auto t=pos[ci[j]]++;src[t]=sr[j];a[t]=va[j];}
 auto act=[&](const vector<uint64_t>&v){vector<uint64_t>w(ns);for(size_t j=0;j<ns;j++){uint64_t z=0;for(size_t lo=off[j];lo<off[j+1];lo+=block){uint64_t part=0;for(size_t h=lo;h<min(off[j+1],lo+block);h++)part+=v[src[h]]*a[h];z=(z+part%q)%q;}w[j]=z;}return w;};
 vector<uint64_t>v(ns,0);if(getenv("STRANGE_RANDOM_START")){for(auto&x:v)x=rng()%q;}else v[eidx]=ec;vector<uint64_t>eis{(2*chi2+1)%q,(chi2+2)%q};if(getenv("STRANGE_EIS")){char*e;eis[0]=strtoull(getenv("STRANGE_EIS"),&e,10)%q;eis[1]=strtoull(e,nullptr,10)%q;}for(uint64_t c:eis){auto w=act(v);for(size_t j=0;j<ns;j++)w[j]=(w[j]+q-mul(c,v[j]))%q;v.swap(w);}
 ofstream out(argv[2]);assert(out);out<<q<<' '<<ns<<' '<<k<<' '<<nnz<<'\n';for(auto x:v)out<<x<<' ';out<<'\n';for(auto x:u)out<<x<<' ';out<<'\n';count=0;
 for(size_t i=0;i<ns;i++){size_t begin=count;while(count<nnz&&sr[count]==i)count++;out<<count-begin<<' ';for(size_t j=begin;j<count;j++)out<<ci[j]<<' '<<va[j]<<' ';out<<'\n';}assert(count==nnz);
 auto w=v;out<<64<<' ';for(size_t step=0;step<64;step++){uint64_t z=0;for(size_t lo=0;lo<ns;lo+=block){uint64_t part=0;for(size_t j=lo;j<min(ns,lo+block);j++)part+=w[j]*u[j];z=(z+part%q)%q;}out<<z<<' ';w=act(w);}out<<'\n';out.close();
 ofstream cert(argv[3]);assert(cert);cert<<"{\"status\":\"PASS\",\"p\":"<<p<<",\"order\":"<<ord<<",\"q\":"<<q<<",\"generators\":"<<ns<<",\"relations\":"<<nr<<",\"relation_rank\":"<<rank<<",\"dimension\":"<<dim<<",\"cuspidal_dimension\":"<<k<<",\"balanced_components\":"<<balanced<<",\"nodes\":[";
 for(size_t r=0;r<nr+1;r++){if(r)cert<<',';cert<<'['<<par[r]<<','<<pe[r]<<','<<component[r]<<','<<lambda[r]<<','<<pivot[r]<<']';}cert<<"]}\n";
 cout<<"S20_MANIN_GRAPH_PREPARED p="<<p<<" order="<<ord<<" q="<<q<<" generators="<<ns<<" relation_rank="<<rank<<" dimension="<<dim<<" cuspidal_dimension="<<k<<" all_relations_checked=true"<<endl;
}
