# Code for extracting daily values from hourly ERA5 data

getting_daily_T.py : extracting daily min, max, and mean of temperature 

getting_daily_ELD.py : extracting hourly moist enthalpy, then calculating daily enthalpy latent days (ELDs). ELDs are defined as the hourly difference between moist enthalpy and a reference moist enthalpy, summed over the day. 

Both scripts require hourly ERA5 temperature and dew point to be downloaded (example download script: rda-2000.py)
