// Najman, github.com/F-Najman/Sd, degree22/optimization/export_graph_fast.m (MIT, see LICENSE-Najman);
// adapted: aux_prime from strange_primes.magma, and the path of core.m in the local Magma installation.
SetQuitOnError(true);SetColumns(0);SetMemoryLimit(12*10^9);SetSeed(20261029);SequenceOut:="unused_export_only";
load "strange_primes.magma";
import "/opt/hpc-lipwig/public/group_software/math/vivaorg_10150005/magma/V2.30-1/package/Geometry/ModSym/core.m":ManinSymbolList,ManSym2termQuotient,ManinSymbolApply,Sparse2Quotient;
p:=StringToInteger(P);n:=StringToInteger(OrderToTest);q:=aux_prime(p);F:=GF(q);G:=DirichletGroup(p,F);chi:=G.1^ExactQuotient(#G,n);assert Order(chi)eq n and n gt 1 and IsEven(chi);tt:=Cputime();ml:=ManinSymbolList(2,p,F);eps:=ValueList(chi);pp:=ml`p1list;A:=MatrixAlgebra(Integers(p),2);
function Apply(h,j)
 ind,scalar:=P1Reduce(pp[j]*h,pp);assert ind gt 0;return <eps[Integers()!scalar],ind>;
end function;
xS:=[Apply(A![0,-1,1,0],j):j in[1..p+1]];xI:=[Apply(A![-1,0,0,1],j):j in[1..p+1]];
rel:=[[j,xS[j][2]]:j in[1..p+1]]cat[[j,xI[j][2]]:j in[1..p+1]];
rc:=[[F!1,xS[j][1]]:j in[1..p+1]]cat[[F!1,-xI[j][1]]:j in[1..p+1]];
sg,sq,sc:=Sparse2Quotient(rel,rc,p+1,F);delete rel;delete rc;delete xS;delete xI;ns:=#sg;print "S20_GRAPH_TWO_TERM",p,n,ns,Cputime(tt);
T:=A![0,-1,1,-1];TT:=A![-1,1,-1,0];mask:=[false:i in[1..p+1]];rels:={@ @};counts:=[0:i in[1..ns]];
for j in[1..p+1]do
 if not mask[j]then
  t:=Apply(T,j);u:=Apply(TT,j);mask[t[2]]:=true;mask[u[2]]:=true;
  rr:=AssociativeArray();for term in[<sc[j],sq[j]>,<t[1]*sc[t[2]],sq[t[2]]>,<u[1]*sc[u[2]],sq[u[2]]>]do
   c,k:=Explode(term);if k ne 0 and c ne 0 then if not IsDefined(rr,k)then rr[k]:=F!0;end if;rr[k]+:=c;end if;
  end for;
  ix:=Sort([k:k in Keys(rr)|rr[k]ne 0]);if #ix gt 0 then key:=[<k,Integers()!(rr[k]/rr[ix[1]])>:k in ix];Include(~rels,key);end if;
 end if;
end for;
for row in rels do for term in row do counts[term[1]]+:=1;end for;end for;
print "S20_GRAPH_RELATION_STRUCTURE",#rels,Max(counts),{*v:v in counts*},Cputime(tt);assert Max(counts)le 2;
A:=MatrixAlgebra(Integers(p),2);HH:=[A![1,0,0,2],A![2,0,0,1],A![2,1,0,1],A![1,0,1,2]];R:=SparseMatrix(F,ns,ns);
for i in[1..ns]do for h in HH do for term in[Apply(h,sg[i])]do c,j:=Explode(term);a:=sq[j];if a ne 0 then R[i,a]+:=c*sc[j];end if;end for;end for;end for;
pp:=ml`p1list;ind:=Position(pp,Parent(pp[1])![0,1]);assert ind gt 0 and sq[ind]gt 0;
PrintFile(GraphOut,Sprintf("%o %o %o %o %o %o %o %o %o",q,p,n,ns,#rels,NNZEntries(R),Integers()!chi(2),sq[ind]-1,Integers()!sc[ind]):Overwrite:=true);
for row in rels do PrintFile(GraphOut,IntegerToString(#row)cat " "cat &cat[IntegerToString(t[1]-1)cat " "cat IntegerToString(t[2])cat " ":t in row]);end for;
for i in[1..ns]do supp:=Support(R,i);PrintFile(GraphOut,IntegerToString(#supp)cat " "cat &cat[IntegerToString(j-1)cat " "cat IntegerToString(Integers()!R[i,j])cat " ":j in supp]);end for;
printf "S20_MANIN_GRAPH_EXPORT_COMPLETE p=%o order=%o q=%o generators=%o relations=%o nnz=%o max_column_degree=%o seconds=%o\n",p,n,q,ns,#rels,NNZEntries(R),Max(counts),Cputime(tt);quit;
