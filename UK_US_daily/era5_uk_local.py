#!/usr/bin/env python3
"""
ERA5 processing for the United Kingdom with timezone conversion.

Loads monthly ERA5 hourly files with a prev/next month buffer (for DST boundary
handling), converts to local timezone (Europe/London), applies the country polygon
mask (fixes the original bbox-average bias from ocean cells), then writes one hourly
CSV and one daily CSV per year.

Side-analysis variant: ELD uses the enthalpy-excess threshold only (no temperature
threshold), and W_REF is set to 0.008 instead of the 0.0116 used elsewhere.
"""
import os
import time
import logging
import warnings
import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
from timezonefinder import TimezoneFinder
import pytz
from collections import Counter
import sys

# Expected artifact of polygon masking: dask processes all-NaN chunks (ocean cells)
# when computing daily max/min. Results are still correct.
warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

# ---- CONFIG ----
DATA_FOLDER   = "/dx03/data/cockburn_era5/downloads"
OUTPUT_FOLDER = "/dx03/data/cockburn_era5/Humidity_Paper/timezone_conversions/hourly_data_tz"
COUNTRIES_SHP = "/home/ccockburn/natural_earth_shapefiles/ne_110m_admin_0_countries.shp"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# (year_start, year_end, CDD base temps dict)
# Base temps are unused by this side-analysis (ELD has no temperature threshold here),
# kept as placeholders matching the Greece values from era5_national_tz.py.
COUNTRY_CONFIGS = {
    "United Kingdom": (2019, 2024, dict(cdd=20.5, hi=20.5, hu=23.5, tw=15.5, q=44.0)),
}

W_REF = 0.008
tf = TimezoneFinder()


# ---- FILE I/O ----

def get_file(year, month, varstr):
    pattern = f".{year}{month:02d}"
    for f in os.listdir(DATA_FOLDER):
        if pattern in f and f.endswith(".nc") and varstr in f:
            return os.path.join(DATA_FOLDER, f)
    return None


def load_with_buffer(year, month, varstr, buffer_hours=13):
    """
    Load current month plus a small time buffer from adjacent files.

    Instead of loading full prev/next month files (~2160 hours total), we only
    take `buffer_hours` from each adjacent file. 13 hours comfortably covers the
    UK's UTC+0/+1 offset. This reduces I/O by roughly 3x compared to the original
    3-month approach.
    """
    parts = []

    # Tail of previous month
    pm, py = (month - 1, year) if month > 1 else (12, year - 1)
    f_prev = get_file(py, pm, varstr)
    if f_prev:
        ds_prev = xr.open_dataset(f_prev, chunks="auto")
        parts.append(ds_prev.isel(time=slice(-buffer_hours, None)))

    # Full current month
    f_curr = get_file(year, month, varstr)
    if f_curr is None:
        return None
    parts.append(xr.open_dataset(f_curr, chunks="auto"))

    # Head of next month
    nm, ny = (month + 1, year) if month < 12 else (1, year + 1)
    f_next = get_file(ny, nm, varstr)
    if f_next:
        ds_next = xr.open_dataset(f_next, chunks="auto")
        parts.append(ds_next.isel(time=slice(None, buffer_hours)))

    ds = xr.concat(parts, dim="time")
    ds = ds.assign_coords(longitude=((ds.longitude + 180) % 360 - 180)).sortby("longitude")
    return ds


# ---- DERIVED VARIABLES (xarray, lazy) ----

def calc_RH(T, Td):
    es = 6.1094 * np.exp((17.625 * T) / (T + 243.04))
    e  = 6.1094 * np.exp((17.625 * Td) / (Td + 243.04))
    RH = 100 * e / es
    return xr.where(RH < 0, 0.0, xr.where(RH > 100, 100.0, RH))


def calc_HI(T, RH):
    T_F  = T * 9 / 5 + 32
    HI_F = (-42.379 + 2.04901523 * T_F + 10.14333127 * RH
            - 0.22475541 * T_F * RH - 6.83783e-3 * T_F**2
            - 5.481717e-2 * RH**2 + 1.22874e-3 * T_F**2 * RH
            + 8.5282e-4 * T_F * RH**2 - 1.99e-6 * T_F**2 * RH**2)
    HI_F = xr.where((T_F < 80) | (RH < 40), T_F, HI_F)
    return (HI_F - 32) * 5 / 9


def calc_Tw(T, RH):
    return (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659))
            + np.arctan(T + RH) - np.arctan(RH - 1.676331)
            + 0.00391838 * RH**1.5 * np.arctan(0.023101 * RH) - 4.686035)


def calc_HU(T, Td):
    e = 6.11 * np.exp(5417.7530 * ((1 / 273.16) - (1 / (273.15 + Td))))
    return T + 0.5555 * (e - 10)


def calc_W(Td, P=1013.25):
    e = 6.112 * np.exp((17.62 * Td) / (243.12 + Td))
    return 0.622 * (e / (P - e))


def calc_Q(T, W):
    return 1.006 * T + W * (2501 + 1.86 * T)


def calc_cdd(tmax, tmean, tmin, tb):
    """Cooling degree days per grid cell (xarray, lazy)."""
    cdd = xr.zeros_like(tmax)
    cdd = xr.where(tmax <= tb, 0.0, cdd)
    cdd = xr.where((tmean <= tb) & (tb < tmax), (tmax - tb) / 4, cdd)
    cdd = xr.where((tmin < tb) & (tb < tmean), (tmax - tb) / 2 - (tb - tmin) / 4, cdd)
    cdd = xr.where(tmin >= tb, tmean - tb, cdd)
    return cdd


# ---- POLYGON MASK ----

def build_mask(lat_vals, lon_vals, polygon):
    """2D boolean array (lat × lon): True where the cell centre is inside the polygon."""
    xx, yy = np.meshgrid(lon_vals, lat_vals)
    pts = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(xx.ravel(), yy.ravel()), crs="EPSG:4326"
    )
    return pts.within(polygon).values.reshape(len(lat_vals), len(lon_vals))


# ---- TIMEZONE DETECTION ----

def get_country_timezone(country_name, country_geom, year_start):
    """
    Detect the dominant IANA timezone for a country by querying cells within the
    polygon from a sample ERA5 file. Called once per country, not per month.
    """
    for month in range(1, 13):
        f = get_file(year_start, month, "2t")
        if f is None:
            continue
        ds = xr.open_dataset(f)
        ds = ds.assign_coords(longitude=((ds.longitude + 180) % 360 - 180)).sortby("longitude")
        minx, miny, maxx, maxy = country_geom.bounds
        buf = 0.5
        ds = ds.sel(latitude=slice(maxy + buf, miny - buf),
                    longitude=slice(minx - buf, maxx + buf))
        lat_vals = ds.latitude.values
        lon_vals = ds.longitude.values
        ds.close()

        mask_2d = build_mask(lat_vals, lon_vals, country_geom)
        xx, yy  = np.meshgrid(lon_vals, lat_vals)
        tz_names = [
            tz for lat, lon, inside in zip(yy.ravel(), xx.ravel(), mask_2d.ravel())
            if inside
            for tz in [tf.timezone_at(lat=float(lat), lng=float(lon))]
            if tz
        ]
        if tz_names:
            result = Counter(tz_names).most_common(1)[0][0]
            logging.info(f"{country_name} timezone: {result}")
            return result

    logging.warning(f"Could not detect timezone for {country_name}; using UTC")
    return "UTC"


# ---- MONTH PROCESSING ----

def process_month(country_name, year, month, country_geom, country_tz, tb):
    logging.info(f"Processing {country_name} {year}-{month:02d}")

    if get_file(year, month, "2t") is None or get_file(year, month, "2d") is None:
        logging.warning(f"Missing ERA5 files for {country_name} {year}-{month:02d}, skipping")
        return None, None

    ds_T  = load_with_buffer(year, month, "2t")
    ds_Td = load_with_buffer(year, month, "2d")
    if ds_T is None or ds_Td is None:
        return None, None

    # Crop to country bbox + buffer
    minx, miny, maxx, maxy = country_geom.bounds
    buf = 0.5
    ds_T  = ds_T.sel(latitude=slice(maxy + buf, miny - buf),
                     longitude=slice(minx - buf, maxx + buf))
    ds_Td = ds_Td.sel(latitude=slice(maxy + buf, miny - buf),
                      longitude=slice(minx - buf, maxx + buf))

    T  = ds_T["VAR_2T"]  - 273.15
    Td = ds_Td["VAR_2D"] - 273.15

    lat_vals = T.latitude.values
    lon_vals = T.longitude.values

    # Polygon mask
    mask_2d = build_mask(lat_vals, lon_vals, country_geom)
    if mask_2d.sum() == 0:
        logging.warning(f"No cells inside {country_name} polygon; falling back to bbox mean")
        mask_2d = np.ones((len(lat_vals), len(lon_vals)), dtype=bool)
    mask_da = xr.DataArray(mask_2d, dims=("latitude", "longitude"))

    # Convert UTC time index to local time, trim to current month
    utc_index   = pd.DatetimeIndex(T.time.values).tz_localize("UTC")
    local_index = utc_index.tz_convert(pytz.timezone(country_tz)).tz_localize(None)
    t0 = pd.Timestamp(year=year, month=month, day=1)
    t1 = (pd.Timestamp(year=year + 1, month=1, day=1) if month == 12
          else pd.Timestamp(year=year, month=month + 1, day=1))
    month_mask = (local_index >= t0) & (local_index < t1)

    T  = T.isel(time=month_mask).assign_coords(time=local_index[month_mask])
    Td = Td.isel(time=month_mask).assign_coords(time=local_index[month_mask])

    # Load bbox data into memory once — small countries so trivial size.
    # Without this, every .values call re-reads the ERA5 files from disk.
    T  = T.load()
    Td = Td.load()

    def mask(da):
        return da.where(mask_da)

    # Derived variables (now in-memory, masked)
    RH = mask(calc_RH(T, Td))
    HI = mask(calc_HI(T, RH))
    Tw = mask(calc_Tw(T, RH))
    HU = mask(calc_HU(T, Td))
    W  = mask(calc_W(Td))
    Q  = mask(calc_Q(T, W))
    Qb = mask(calc_Q(T, W_REF))
    T  = mask(T)
    Td = mask(Td)

    def smean(da):
        return da.mean(("latitude", "longitude"), skipna=True)

    def ssum(da):
        return da.sum(("latitude", "longitude"), skipna=True)

    # ---- HOURLY OUTPUT ----
    hourly_df = pd.DataFrame({
        "country":    country_name,
        "timezone":   country_tz,
        "time_local": T.time.values,
        "T":   smean(T).values,
        "Td":  smean(Td).values,
        "RH":  smean(RH).values,
        "HI":  smean(HI).values,
        "Tw":  smean(Tw).values,
        "HU":  smean(HU).values,
        "W":   smean(W).values,
        "Q":   smean(Q).values,
        "Qb":  smean(Qb).values,
    })

    # ---- DAILY OUTPUT ----
    def daily_stats(da):
        return da.resample(time="1D").mean(), da.resample(time="1D").max(), da.resample(time="1D").min()

    T_dmean,  T_dmax,  T_dmin  = daily_stats(T)
    HI_dmean, HI_dmax, HI_dmin = daily_stats(HI)
    Tw_dmean, Tw_dmax, Tw_dmin = daily_stats(Tw)
    HU_dmean, HU_dmax, HU_dmin = daily_stats(HU)
    Q_dmean,  Q_dmax,  Q_dmin  = daily_stats(Q)
    Td_dmean = Td.resample(time="1D").mean()
    RH_dmean = RH.resample(time="1D").mean()

    # CDD summed over polygon cells, consistent with subnational approach
    cdd_m   = ssum(calc_cdd(T_dmax,  T_dmean,  T_dmin,  tb["cdd"]))
    cddhi_m = ssum(calc_cdd(HI_dmax, HI_dmean, HI_dmin, tb["hi"]))
    cddhu_m = ssum(calc_cdd(HU_dmax, HU_dmean, HU_dmin, tb["hu"]))
    cddtw_m = ssum(calc_cdd(Tw_dmax, Tw_dmean, Tw_dmin, tb["tw"]))
    cddq_m  = ssum(calc_cdd(Q_dmax,  Q_dmean,  Q_dmin,  tb["q"]))

    Q_excess = (Q - Qb) * (Q > Qb).astype(float)
    eld_m = ssum(Q_excess.resample(time="1D").sum()) / 24

    daily_df = pd.DataFrame({
        "country":    country_name,
        "timezone":   country_tz,
        "date_local": T_dmean.time.values,
        "T":       smean(T_dmean).values,
        "Td":      smean(Td_dmean).values,
        "RH":      smean(RH_dmean).values,
        "HI":      smean(HI_dmean).values,
        "Tw":      smean(Tw_dmean).values,
        "HU":      smean(HU_dmean).values,
        "Q":       smean(Q_dmean).values,
        "CDD":     cdd_m.values,
        "CDDhi":   cddhi_m.values,
        "CDDhu":   cddhu_m.values,
        "CDDtw":   cddtw_m.values,
        "CDDq":    cddq_m.values,
        "ELD":     eld_m.values,
    })

    return hourly_df, daily_df


# ---- MAIN ----

def main():
    countries_gdf = gpd.read_file(COUNTRIES_SHP).rename(columns={"ADMIN": "Country"})

    for country_name, (ystart, yend, tb) in COUNTRY_CONFIGS.items():
        t_country = time.time()
        found = countries_gdf[countries_gdf["Country"] == country_name]
        if found.empty:
            logging.warning(f"{country_name} not found in shapefile, skipping")
            continue
        country_geom = found.geometry.values[0]

        # Detect timezone once per country (not per month)
        country_tz = get_country_timezone(country_name, country_geom, ystart)

        for year in range(ystart, yend + 1):
            t_year = time.time()
            hourly_rows, daily_rows = [], []

            for month in range(1, 13):
                t_month = time.time()
                try:
                    h_df, d_df = process_month(
                        country_name, year, month, country_geom, country_tz, tb
                    )
                    if h_df is not None:
                        hourly_rows.append(h_df)
                        daily_rows.append(d_df)
                except Exception as e:
                    logging.exception(f"Error {country_name} {year}-{month:02d}: {e}")
                logging.info(f"Done {country_name} {year}-{month:02d} in {time.time() - t_month:.1f}s")

            if hourly_rows:
                df_hourly = pd.concat(hourly_rows, ignore_index=True)
                df_daily  = pd.concat(daily_rows,  ignore_index=True)

                # DST sanity check: every day should have 23–25 hours
                counts = df_hourly.groupby(df_hourly.time_local.dt.date).size()
                if counts.min() < 23 or counts.max() > 25:
                    logging.warning(
                        f"{country_name} {year}: unusual day lengths "
                        f"(min={counts.min()}, max={counts.max()}) — check DST handling"
                    )

                cname = country_name.replace(" ", "_")
                df_hourly.to_csv(
                    os.path.join(OUTPUT_FOLDER, f"era5_hourly_{cname}_{year}_local.csv"), index=False)
                df_daily.to_csv(
                    os.path.join(OUTPUT_FOLDER, f"era5_daily_{cname}_{year}_local.csv"), index=False)
                logging.info(f"Saved {country_name} {year} in {(time.time() - t_year) / 60:.1f} min")
            else:
                logging.warning(f"No data for {country_name} {year}")

        logging.info(f"Finished {country_name} in {(time.time() - t_country) / 60:.1f} min")


if __name__ == "__main__":
    main()
