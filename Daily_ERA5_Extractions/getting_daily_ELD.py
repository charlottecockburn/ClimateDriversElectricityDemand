import xarray as xr
import os
import numpy as np
import re
import time
import sys
import dask

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

def calculate_vapor_pressure(T):
    """Saturation vapor pressure (hPa) using temperature in Celsius."""
    return 6.112 * np.exp((17.62 * T) / (243.12 + T))

def calculate_specific_humidity_ratio(Td, P):
    """Compute humidity ratio W (kg/kg dry air) from dew point and pressure."""
    e = calculate_vapor_pressure(Td)
    return 0.622 * (e / (P - e))

def calculate_enthalpy(T, W):
    """Calculate moist air enthalpy (kJ/kg dry air)."""
    return 1.006 * T + W * (2501 + 1.86 * T)

# Constants
W_ref = 0.008
T_threshold = -100  # no effective threshold

# Paths
data_folder = "/dx03/data/cockburn_era5/downloads"
output_folder = "/dx03/data/cockburn_era5/daily_data"

years = [str(y) for y in range(2000, 2025)]

# 24h time chunks align perfectly with daily resample; spatial split keeps
# each chunk manageable on the full 721x1440 ERA5 grid (~180 MB per chunk).
CHUNKS = {"time": 24, "latitude": 181, "longitude": 360}

ENCODING = {v: {"zlib": True, "complevel": 4}
            for v in ["ELD", "Q_mean", "Q_min", "Q_max", "Qb_mean"]}

for file in sorted(os.listdir(data_folder)):
    if not (file.endswith(".nc") and "2d" in file and any(y in file for y in years)):
        continue

    start_time = time.time()

    file_path      = os.path.join(data_folder, file)
    temp_file_path = os.path.join(data_folder, file.replace("2d", "2t").replace("168", "167"))
    pres_file_path = os.path.join(data_folder, file.replace("2d", "sp").replace("168", "134"))

    if not (os.path.exists(temp_file_path) and os.path.exists(pres_file_path)):
        print(f"Skipping {file}: companion file missing")
        continue

    print(f"Processing {file}...")

    ds_dew  = xr.open_dataset(file_path,       chunks=CHUNKS)
    ds_temp = xr.open_dataset(temp_file_path,  chunks=CHUNKS)
    ds_pres = xr.open_dataset(pres_file_path,  chunks=CHUNKS)

    Td = ds_dew["VAR_2D"]  - 273.15
    T  = ds_temp["VAR_2T"] - 273.15
    P  = ds_pres["SP"]     / 100
    Td, T, P = xr.align(Td, T, P, join="exact")

    W  = calculate_specific_humidity_ratio(Td, P)
    Q  = calculate_enthalpy(T, W)
    Qb = calculate_enthalpy(T, W_ref)

    Q_diff  = xr.where((T > T_threshold) & (Q > Qb), Q - Qb, 0)

    ELD     = Q_diff.resample(time="1D").sum() / 24
    Q_mean  = Q.resample(time="1D").mean()
    Q_min   = Q.resample(time="1D").min()
    Q_max   = Q.resample(time="1D").max()
    Qb_mean = Qb.resample(time="1D").mean()

    # Single graph traversal: W → Q → Qb computed once for all outputs
    ELD_c, Qm_c, Qmin_c, Qmax_c, Qb_c = dask.compute(
        ELD, Q_mean, Q_min, Q_max, Qb_mean
    )

    ds_daily = xr.Dataset({
        "ELD":    ELD_c,
        "Q_mean": Qm_c,
        "Q_min":  Qmin_c,
        "Q_max":  Qmax_c,
        "Qb_mean": Qb_c,
    })

    match = re.search(r'(\d{4})(\d{2})\d{2}', file)
    year, month = match.groups()
    output_file = os.path.join(output_folder, f"era5_daily_eld2_{year}_{month}.nc")

    ds_daily.to_netcdf(output_file, engine="netcdf4", encoding=ENCODING)

    ds_dew.close(); ds_temp.close(); ds_pres.close()

    print(f"Done in {time.time() - start_time:.2f}s: {output_file}")
