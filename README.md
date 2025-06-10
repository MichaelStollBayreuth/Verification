# Verification

This repository contains files with (mostly [Magma](https://magma.maths.usyd.edu.au/magma/)) code
for verifying computational assertions in some of my papers.

## The Generalized Fermat Equation $x^2 + y^3 = z^{25}$

(With Nuno Freitas)

A file with Magma code verifying the claims in the paper is [here](GenFermat_2_3_25/2_3_25.magma)

**NOTE** When running this with a version of Magma up to and including 2.28-23,
the computation of the first Selmer set in Section 7 produces an error.
This (and some similar errors) should be fixed in one of the next releases of Magma.

## The surface parametrizing cuboids

(With Damiano Testa; [arXiv](https://arxiv.org/abs/1009.0388))

* [cuboids.magma](Cuboids/cuboids.magma):
  this contains code to verify many of the computationsl results.

* [Section5_fibrations.magma](Cuboids/Section5_fibrations.log):
  this is the log of a Magma session computing the fibrations given in Section 5.

## Prime numbers and dynamics of the polynomial $x^2 - 1$

(With Ivan Penkov; [arXiv](https://arxiv.org/abs/2502.11929))

The file [Penkov_question.magma](PenkovQuestion/Penkov_question.magma)
contains code to verify the results in Section 3.

## Torsion points on elliptic curves over number fields of small degree

(With Maarten Derickx, Sheldon Kamienny and William Stein;
[arXiv](arxiv.org/abs/1707.00364); [DOI](https://doi.org/10.2140/ant.2023.17.267))

* [DKSS.magma](DKSS/DKSS.magma):
  this contains code for verifying the computational results in the paper.

* [X1_p.magma](DKSS/X1_p.magma):
  this contains equations for models of $X_1(p)$ for the relevant primes $p$;
  this file is loaded by DKSS.magma.

## The Weierstrass root finder is not generally convergent

(With Bernhard Reinke and Dierk Schleicher;
[arXiv](arxiv.org/abs/2004.04777); [DOI](https://doi.org/10.1090/mcom/3783))

The file [Weierstrass-check.magma](Weierstrass/Weierstrass-check.magma)
contains code to verify the results in Section 5.

## Irreducibility of polynomials with a large gap

(With Will Sawin and Mark Shusterman;
[arXiv](arxiv.org/abs/1803.10811); [DOI](https://doi.org/10.4064/aa180526-12-6))

The file [SaShSt-polynomials.magma](SaShSt/SaShSt-polynomials.magma)
contains Magma programs related to the paper.

## An application of ``Selmer group Chabauty'' to arithmetic dynamics

([arXiv](arxiv.org/abs/1912.05893))

* [SelChabDyn.magma](SelChabDyn/SelChabDyn.magma):
  this implements the algorithm described in Section 2 for curves of the form
  $y^2 = x^{2g+1} + h(x)^2$ with $h$ of degree at most $g$, integral coefficients
  and such that $h(0)$ is odd and $h(1)$ is even.

* [SelChabDyn-examples.magma](SelChabDyn/SelChabDyn-examples.magma):
  this verifies the results in Section 3.

## Diagonal genus 5 curves, elliptic curves over ${\mathbb Q}(t)$, and diophantine quintuples

([arXiv](arxiv.org/abs/1711.00500); [DOI](https://doi.org/10.4064/aa180416-4-10))

* [diophtuples.magma](DiophQuintuples/diophtuples.magma):
  this implements the algorithm described in Section 2 (assuming GRH)
  for curves arising from diophantine quadruples.

* [diophtuples-verify.magma](DiophQuintuples/diophtuples-verify.magma):
  this verifies the results (if feasible, without assuming GRH),
  given information on the elliptic curve that gives a ``good'' rank bound.

* [ellQt.magma](DiophQuintuples/ellQt.magma):
  this implements the algorithm described in Section 5.

## The generalized Fermat equation with exponents 2, 3, $n$

(With Bartosz Naskręcki and Nuno Freitas;
[arXiv](https://arxiv.org/abs/1703.05058); [DOI](https://doi.org/10.1112/S0010437X19007693))

* [GenFermat.tar.gz](GenFermat_2_3_p/GenFermat.tar.gz):
  a compressed tarball containing all of the following files.

* [main.magma](GenFermat_2_3_p/main.magma):
  this loads the following four files and so verifies everything.

* [section3.magma](GenFermat_2_3_p/section3.magma):
  this checks the computations in Section 3.

* [section5.magma](GenFermat_2_3_p/section5.magma):
  this checks the computations in Section 5.

* [section7.magma](GenFermat_2_3_p/section7.magma):
  this checks the computations in Section 7.

* [section8.magma](GenFermat_2_3_p/section8.magma):
  this checks the computations in Section 8.

* [localtest.magma](GenFermat_2_3_p/localtest.magma):
  this contains some auxiliary functions and is loaded by section7.magma.

* [X1_13_opt.magma](GenFermat_2_3_p/X1_13_opt.magma):
  this contains some auxiliary functions and is loaded by section8.magma.
