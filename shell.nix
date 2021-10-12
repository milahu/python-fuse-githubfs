{
  pkgs ? import <nixpkgs> {}
}:

let
  my-python = pkgs.python39;

  my-python-packages = python-packages: with python-packages; [

# requirements.txt


boto3
diskcache
numpy
certifi
idna
#fuse
fusepy
tenacity

#pysort # TODO add to nixpkgs

/*
atomiclong
cffi
fusepy
pycparser
pygit2
raven
six
*/

  ]; 
  python-with-my-packages = my-python.withPackages my-python-packages;
in
python-with-my-packages.env

