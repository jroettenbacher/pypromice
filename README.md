# pypromice
[![](<https://img.shields.io/badge/Dataverse DOI-10.22008/FK2/3TSBF0-orange>)](https://www.doi.org/10.22008/FK2/3TSBF0) [![Documentation Status](https://readthedocs.org/projects/pypromice/badge/?version=latest)](https://pypromice.readthedocs.io/en/latest/?badge=latest)
 
pypromice is designed for processing and handling [PROMICE](https://promice.dk) automated weather station (AWS) data.

It is envisioned for pypromice to be the go-to toolbox for handling and processing [PROMICE](https://promice.dk) and [GC-Net](http://cires1.colorado.edu/steffen/gcnet/) datasets. New releases of pypromice are uploaded alongside PROMICE AWS data releases to our [Dataverse](https://dataverse.geus.dk/dataverse/PROMICE) for transparency purposes and to encourage collaboration on improving our data. Please visit the pypromice [readthedocs](https://pypromice.readthedocs.io/en/latest/?badge=latest) for more information. 

If you intend to use PROMICE AWS data and/or pypromice in your work, please cite these publications below, along with any other applicable PROMICE publications where possible:

**Fausto, R.S., van As, D., Mankoff, K.D., Vandecrux, B., Citterio, M., Ahlstrøm, A.P., Andersen, S.B., Colgan, W., Karlsson, N.B., Kjeldsen, K.K., Korsgaard, N.J., Larsen, S.H., Nielsen, S., Pedersen, A.Ø., Shields, C.L., Solgaard, A.M., and Box, J.E. (2021) Programme for Monitoring of the Greenland Ice Sheet (PROMICE) automatic weather station data, Earth Syst. Sci. Data, 13, 3819–3845, [https://doi.org/10.5194/essd-13-3819-2021](https://doi.org/10.5194/essd-13-3819-2021)**

**How, P., Wright, P.J., Mankoff, K., Vandecrux, B. (2023) pypromice, GEUS Dataverse, [https://doi.org/10.22008/FK2/3TSBF0](https://doi.org/10.22008/FK2/3TSBF0)** 


## Installation

### Quick install

pypromice can installed using pip:

```
$ pip install --upgrade git+http://github.com/GEUS-Glaciology-and-Climate/pypromice.git
```

### Developer install
	
pypromice can be ran in an environment with the specified dependencies.

```
$ conda create --name pypromice python=3.8
$ conda activate pypromice
$ conda install xarray pandas pathlib
$ conda install -c conda-forge netCDF4
```

With the pypromice package cloned from here.

```
$ git clone git@github.com:GEUS-Glaciology-and-Climate/pypromice.git
```

### Additional dependencies

Additional packages are required if you wish to use pypromice's post-processing functionality. 


#### scikit-learn

[scikit-learn](https://scikit-learn.org/stable/) can installed with conda-forge.

```
$ conda install -c conda-forge scikit-learn
```

Or with pip. 

```
$ pip install scikit-learn 
```

#### eccodes

[eccodes](https://confluence.ecmwf.int/display/ECC/ecCodes+installation) is the official package for BUFR encoding and decoding. Try firstly to install with conda-forge like so:

```
$ conda install -c conda-forge eccodes
```

If the environment cannot resolve the eccodes installation then follow the steps documented [here](https://gist.github.com/MHBalsmeier/a01ad4e07ecf467c90fad2ac7719844a) to download eccodes and then install eccodes' python bindings using pip.

```
$ pip3 install eccodes-python
```
