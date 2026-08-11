# ClimateDriversElectricityDemand
Code for paper: Assessing the Climate Drivers of Global Electricity Demand

## OVERVIEW 

AssessingDrivers_Final_Aug2026.pynb : Jupyter notebook containing all statistical modeling and figures for the paper. Data can be found here. 

Daily_ERA5_Extractions : Folder containing scripts for extracting daily minimum, maximum, and averages temperature and dew point temperature from the raw ERA5 hourly data, which can be found [here](https://gdex.ucar.edu/datasets/d633000/). 

Monthly_ERA5_Extractions: Folder containing scripts for extracting monthly temperature and cooling degree-days from the intermediate files produced by the daily extractions. 

Input_data: Temporary storage of end-stage data to support the review process. These files contain all data needed to replicate figures, tables and other analyses (using AssessingDrivers_Final_Aug2026.pynb). These files, along with intermediate ERA5 netCDF files, will be moved to a final repository on Zenodo upon acceptance. 

UK_US_Daily: Folder containing all files necessary to generate the submonthly response curves in the main script
