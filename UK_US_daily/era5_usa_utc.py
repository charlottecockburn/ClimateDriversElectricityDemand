#!/usr/bin/env python3
"""
ERA5 processing for US Balancing Authorities in UTC — no timezone conversion.

Reads monthly ERA5 hourly files from downloads/, crops to the US bounding box,
computes derived climate variables, spatially joins each grid cell to its
Balancing Authority, and writes one hourly CSV and one daily CSV per year.

Daily statistics and CDDs are derived from the BA-aggregated hourly data so
no separate daily ERA5 files are needed.
"""
import os
import time
import logging
import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

# ---- CONFIG ----
DATA_FOLDER   = "/dx03/data/cockburn_era5/downloads"
OUTPUT_FOLDER = "/dx03/data/cockburn_era5/Humidity_Paper/timezone_conversions/hourly_data_tz"
COUNTRIES_SHP = "/home/ccockburn/natural_earth_shapefiles/ne_110m_admin_0_countries.shp"
US_BA_SHP     = "/dx03/data/cockburn_era5/Humidity_Paper/USA/ba_shapes/Balancing_Authorities.shp"

YEAR_START = 2019
YEAR_END   = 2024

W_REF = 0.008   # reference specific humidity ratio for enthalpy baseline
# US CDD base temperatures (°C)
TB = dict(cdd=15.0, hi=14.5, hu=14.5, tw=10.0, q=27.5)

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ---- FILE I/O ----

def get_file(year, month, varstr):
    pattern = f"sc.{year}{month:02d}"
    for f in os.listdir(DATA_FOLDER):
        if pattern in f and f.endswith(".nc") and varstr in f:
            return os.path.join(DATA_FOLDER, f)
    logging.warning(f"Could not find file matching pattern '{pattern}' for var '{varstr}'")
    return None


def load_month(year, month, varstr):
    f = get_file(year, month, varstr)
    if f is None:
        return None
    ds = xr.open_dataset(f, chunks="auto")
    # ERA5 longitudes are 0–360; convert to -180..180 and sort
    ds = ds.assign_coords(longitude=((ds.longitude + 180) % 360 - 180)).sortby("longitude")
    return ds


# ---- DERIVED VARIABLES (numpy — .values extracted before calling) ----

def calc_RH(T, Td):
    es = 6.1094 * np.exp((17.625 * T) / (T + 243.04))
    e  = 6.1094 * np.exp((17.625 * Td) / (Td + 243.04))
    return np.clip(100 * e / es, 0, 100)


def calc_HI(T, RH):
    T_F  = T * 9 / 5 + 32
    HI_F = (-42.379 + 2.04901523 * T_F + 10.14333127 * RH
            - 0.22475541 * T_F * RH - 6.83783e-3 * T_F**2
            - 5.481717e-2 * RH**2 + 1.22874e-3 * T_F**2 * RH
            + 8.5282e-4 * T_F * RH**2 - 1.99e-6 * T_F**2 * RH**2)
    HI_F = np.where((T_F < 80) | (RH < 40), T_F, HI_F)
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


def calculate_cdd(tmax, tmean, tmin, tb):
    """Cooling degree days (numpy arrays)."""
    cdd = np.zeros_like(tmax)
    cdd = np.where(tmax <= tb, 0.0, cdd)
    cdd = np.where((tmean <= tb) & (tb < tmax), (tmax - tb) / 4, cdd)
    cdd = np.where((tmin < tb) & (tb < tmean), (tmax - tb) / 2 - (tb - tmin) / 4, cdd)
    cdd = np.where(tmin >= tb, tmean - tb, cdd)
    return cdd


# ---- GRID→BA MAPPING (built once, reused every month) ----

def build_grid_ba_mapping(ba_gdf, lat_vals, lon_vals):
    """Spatial join on ~N_lat×N_lon unique grid points — run once, not per month.

    Returns flat indices into the (n_lat × n_lon) grid that fall inside a BA,
    and the corresponding EIAcode for each such cell.
    """
    lons_2d, lats_2d = np.meshgrid(lon_vals, lat_vals)
    n = lons_2d.size
    grid_gdf = gpd.GeoDataFrame(
        {"_idx": np.arange(n)},
        geometry=gpd.points_from_xy(lons_2d.ravel(), lats_2d.ravel()),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(grid_gdf, ba_gdf[["geometry", "EIAcode"]].rename(columns={"EIAcode": "Sector"}), how="inner", predicate="intersects")
    return joined["_idx"].values, joined["Sector"].values


def _init_grid_info(ba_gdf, country_geom):
    """Load the first available ERA5 file, crop it, and build the grid→BA mapping."""
    minx, miny, maxx, maxy = country_geom.bounds
    buf = 0.5
    for year in range(YEAR_START, YEAR_END + 1):
        for month in range(1, 13):
            ds = load_month(year, month, "2t")
            if ds is None:
                continue
            ds = ds.sel(latitude=slice(maxy + buf, miny - buf),
                        longitude=slice(minx - buf, maxx + buf))
            lat_vals = ds.latitude.values.astype("float32")
            lon_vals = ds.longitude.values.astype("float32")
            logging.info("Building grid→BA mapping (one-time)...")
            cell_idx, sectors = build_grid_ba_mapping(ba_gdf, lat_vals, lon_vals)
            logging.info(
                f"Mapping built: {len(cell_idx)} valid cells across "
                f"{len(np.unique(sectors))} sectors"
            )
            return {
                "lat": lat_vals, "lon": lon_vals,
                "cell_idx": cell_idx, "sectors": sectors,
                "bounds": country_geom.bounds,
            }
    raise RuntimeError("No ERA5 files found — cannot initialise grid mapping")


# ---- MONTH PROCESSING ----

def process_month(year, month, country_geom, grid_info):
    logging.info(f"Processing USA {year}-{month:02d}")

    ds_T  = load_month(year, month, "2t")
    ds_Td = load_month(year, month, "2d")
    if ds_T is None or ds_Td is None:
        logging.warning(f"Missing ERA5 files for {year}-{month:02d}, skipping")
        return None, None

    # Crop to US bounding box + buffer before extracting values
    minx, miny, maxx, maxy = country_geom.bounds
    buf = 0.5
    ds_T  = ds_T.sel(latitude=slice(maxy + buf, miny - buf),
                     longitude=slice(minx - buf, maxx + buf))
    ds_Td = ds_Td.sel(latitude=slice(maxy + buf, miny - buf),
                      longitude=slice(minx - buf, maxx + buf))

    # Extract to numpy — avoids repeated dask graph overhead for US-scale operations
    T_arr  = (ds_T["VAR_2T"].values  - 273.15).astype("float32")
    Td_arr = (ds_Td["VAR_2D"].values - 273.15).astype("float32")

    time_vals = pd.to_datetime(ds_T.time.values)
    n_time, n_lat, n_lon = T_arr.shape

    # Derived variables
    RH_arr = calc_RH(T_arr, Td_arr)
    HI_arr = calc_HI(T_arr, RH_arr)
    Tw_arr = calc_Tw(T_arr, RH_arr)
    HU_arr = calc_HU(T_arr, Td_arr)
    W_arr  = calc_W(Td_arr)
    Q_arr  = calc_Q(T_arr, W_arr)
    Qb_arr = calc_Q(T_arr, W_REF)
    logging.info("Derived vars computed, building DataFrame...")

    # Use pre-computed mapping: select only cells that fall inside a BA
    cell_idx = grid_info["cell_idx"]  # flat indices into (n_lat * n_lon)
    sectors  = grid_info["sectors"]
    n_cells  = len(cell_idx)

    def sel(arr):
        return arr.reshape(n_time, -1)[:, cell_idx].ravel()

    flat = {
        "time_utc": np.repeat(time_vals, n_cells),
        "Sector":   np.tile(sectors, n_time),
        "cell":     np.tile(np.arange(n_cells), n_time),
        "T":   sel(T_arr),
        "Td":  sel(Td_arr),
        "RH":  sel(RH_arr),
        "HI":  sel(HI_arr),
        "Tw":  sel(Tw_arr),
        "HU":  sel(HU_arr),
        "W":   sel(W_arr),
        "Q":   sel(Q_arr),
        "Qb":  sel(Qb_arr),
    }
    df = pd.DataFrame(flat)

    if df.empty:
        logging.warning(f"No in-BA cells for {year}-{month:02d}")
        return None, None

    logging.info("Aggregating...")

    # ---- HOURLY: mean per BA per UTC hour ----
    clim_cols = ["T", "Td", "RH", "HI", "Tw", "HU", "W", "Q", "Qb"]
    hourly = (
        df.groupby(["Sector", "time_utc"])[clim_cols]
        .mean()
        .reset_index()
    )

    # ---- DAILY: compute CDD per grid cell then sum by BA ----
    # Working from the raw per-cell hourly data so that CDD is summed over
    # cells within each BA — consistent with original approach.
    df["date_utc"] = df["time_utc"].dt.floor("D")
    group_cell = ["Sector", "cell", "date_utc"]
    group_day  = ["Sector", "date_utc"]

    maxmin_cols = ["T", "HI", "Tw", "HU", "Q"]
    mean_cols   = ["T", "Td", "RH", "HI", "Tw", "HU", "W", "Q"]

    cell_mean = df.groupby(group_cell)[mean_cols].mean().reset_index()
    cell_max  = df.groupby(group_cell)[maxmin_cols].max().rename(
        columns={c: f"{c}_max" for c in maxmin_cols}).reset_index()
    cell_min  = df.groupby(group_cell)[maxmin_cols].min().rename(
        columns={c: f"{c}_min" for c in maxmin_cols}).reset_index()
    cell_daily = cell_mean.merge(cell_max, on=group_cell).merge(cell_min, on=group_cell)

    # CDD per grid cell
    cell_daily["CDD"]   = calculate_cdd(cell_daily["T_max"].values,  cell_daily["T"].values,  cell_daily["T_min"].values,  TB["cdd"])
    cell_daily["CDDhi"] = calculate_cdd(cell_daily["HI_max"].values, cell_daily["HI"].values, cell_daily["HI_min"].values, TB["hi"])
    cell_daily["CDDhu"] = calculate_cdd(cell_daily["HU_max"].values, cell_daily["HU"].values, cell_daily["HU_min"].values, TB["hu"])
    cell_daily["CDDtw"] = calculate_cdd(cell_daily["Tw_max"].values, cell_daily["Tw"].values, cell_daily["Tw_min"].values, TB["tw"])
    cell_daily["CDDq"]  = calculate_cdd(cell_daily["Q_max"].values,  cell_daily["Q"].values,  cell_daily["Q_min"].values,  TB["q"])

    # ELD per grid cell: sum hourly excess then normalise
    df["Q_excess"] = np.where(df["W"] > W_REF, df["Q"] - df["Qb"], 0.0)
    cell_eld = (df.groupby(group_cell)["Q_excess"].sum() / 24).reset_index().rename(
        columns={"Q_excess": "ELD"})
    cell_daily = cell_daily.merge(cell_eld, on=group_cell)

    # Aggregate to BA level: sum CDDs and ELD, mean temperatures
    cdd_cols  = ["CDD", "CDDhi", "CDDhu", "CDDtw", "CDDq", "ELD"]
    daily_cdd  = cell_daily.groupby(group_day)[cdd_cols].sum().reset_index()
    daily_temp = cell_daily.groupby(group_day)[mean_cols].mean().reset_index()
    daily = daily_temp.merge(daily_cdd, on=group_day)

    return hourly.drop(columns=["Qb"]), daily


# ---- MAIN ----

def main():
    countries_gdf = gpd.read_file(COUNTRIES_SHP).rename(columns={"ADMIN": "Country"})
    found = countries_gdf[countries_gdf["Country"] == "United States of America"]
    if found.empty:
        raise ValueError(f"United States of America not found in {COUNTRIES_SHP}")
    country_geom = found.geometry.values[0]

    ba_gdf = gpd.read_file(US_BA_SHP).to_crs(epsg=4326)

    # Spatial join runs once here, not once per month
    grid_info = _init_grid_info(ba_gdf, country_geom)

    for year in range(YEAR_START, YEAR_END + 1):
        t_year = time.time()
        hourly_rows, daily_rows = [], []

        for month in range(1, 13):
            t_month = time.time()
            try:
                h_df, d_df = process_month(year, month, country_geom, grid_info)
                if h_df is not None:
                    hourly_rows.append(h_df)
                    daily_rows.append(d_df)
            except Exception as e:
                logging.exception(f"Error {year}-{month:02d}: {e}")
            logging.info(f"Done {year}-{month:02d} in {time.time() - t_month:.1f}s")

        if hourly_rows:
            pd.concat(hourly_rows, ignore_index=True).to_csv(
                os.path.join(OUTPUT_FOLDER, f"era5_hourly_USA_{year}_utc2.csv"), index=False)
            pd.concat(daily_rows, ignore_index=True).to_csv(
                os.path.join(OUTPUT_FOLDER, f"era5_daily_USA_{year}_utc2.csv"), index=False)
            logging.info(f"Saved {year} in {(time.time() - t_year) / 60:.1f} min")
        else:
            logging.warning(f"No data produced for {year}")


if __name__ == "__main__":
    main()
