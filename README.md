# Verification

This repository contains files with (mostly Magma) code for verifying computational assertions in some of my papers.

## The Generalized Fermat Equation $x^2 + y^3 = z^{25}$

(With Nuno Freitas)

A file with Magma code verifying the claims in the paper is [here](GenFermat_2_3_25/2_3_25.magma)

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

(With Maarten Derickx, Sheldon Kamienny and William Stein; [arXiv](arxiv.org/abs/1707.00364))

* [DKSS.magma](DKSS/DKSS.magma):
  this contains code for verifying the computational results in the paper.

* [X1_p.magma](DKSS/X1_p.magma):
  this contains equations for models of $X_1(p)$ for the relevant primes $p$;
  this file is loaded by DKSS.magma.
