import xarray as xr
import os
import numpy as np
import re
import time
import sys

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

# File paths
data_folder = "/dx03/data/cockburn_era5/downloads"
output_folder = "/dx03/data/cockburn_era5/daily_data"
#data_folder = "/Users/charlottecockburn/Documents/Columbia/AC_project/remote_deela/download_scripts"
#output_folder = "/Users/charlottecockburn/Documents/Columbia/"

years = [str(y) for y in range(2010, 2025)]

for file in sorted(os.listdir(data_folder)):
    if file.endswith(".nc") and "2t" in file and any(year in file for year in years):
        start_time = time.time()

        file_path = os.path.join(data_folder, file)

        print(f"Processing {file}...")

        # Open with dask
        ds_temp = xr.open_dataset(file_path, chunks={"time": "auto"})
        T = ds_temp["VAR_2T"] - 273.15

        # Calculate RH and HI using xarray

        T_mean = T.groupby(T.time.dt.floor("D")).mean("time")
        T_min = T.groupby(T.time.dt.floor("D")).min("time")
        T_max = T.groupby(T.time.dt.floor("D")).max("time")

        print("got daily means")

        # Construct new dataset
        ds_daily = xr.Dataset({
            "T_mean": T_mean.compute(),
            "T_min": T_min.compute(),
            "T_max": T_max.compute()
        })

        # Generate new filename
        match = re.search(r'(\d{4})(\d{2})\d{2}', file)
        year, month = match.groups()
        new_filename = f"era5_daily_temp_{year}_{month}.nc"
        output_file = os.path.join(output_folder, new_filename)
        
        # Save to NetCDF efficiently
        ds_daily.to_netcdf(output_file, engine="netcdf4", compute=False)

        print(f"Processed and saved in {time.time() - start_time:.2f} seconds: {output_file}")

