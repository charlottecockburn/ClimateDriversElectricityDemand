# UK_US_daily

US_UK_daily_parsing.pynb : Jupyter notebook performing QC on hourly electricity data for the US and UK, then linking it to the era5 climate data generated in era5_uk_local.py and era5_usa_utc.py

era5_uk_local.py: extracts temperature and ELD for the UK at the daily scale, in the correct timezone. 

era5_usa_utc.py: extracts temperature and ELD for the USA at the daily scale in UTC (matches electricity data)
uk_hourly: QC-ed hourly UK electricity data 

** USA electricity data was too large to upload but was retrieved from the EIA. **
