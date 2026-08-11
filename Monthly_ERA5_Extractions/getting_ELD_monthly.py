import os
import xarray as xr
import numpy as np
import pandas as pd
import geopandas as gpd
import time
import psutil
import sys

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

def convert_longitudes(lon):
    """Convert longitudes from 0-360 to -180-180."""
    return (lon + 180) % 360 - 180


def monitor_memory(step=""):
    """Prints the current memory usage."""
    process = psutil.Process(os.getpid())
    print(f"Memory usage after {step}: {process.memory_info().rss / 1024 ** 2:.2f} MB")


data_path = '/dx03/data/cockburn_era5/daily_data'
shapefile_path = '/home/ccockburn/natural_earth_shapefiles/ne_110m_admin_0_countries.shp'
countries = gpd.read_file(shapefile_path)
countries = countries.rename(columns={"ADMIN": "Country"})

# Cached grid-to-country lookup; built once from the first file encountered
grid_to_country = None

for year in range(2000, 2025):
    year_results = []

    for month in range(1, 13):
        print(year, ':', month)
        start_time = time.time()
        file_name = f"era5_daily_eld2_{year}_{month:02d}.nc"
        file_path = os.path.join(data_path, file_name)

        if os.path.exists(file_path):
            ds = xr.open_dataset(file_path)

            # Vectorized mean over the time axis — no Python loops
            # make sure we are SUMMING over time for ELD 
            avg_ELD = ds['ELD'].values.sum(axis=0)    # shape: (lat, lon)
            avg_Q   = ds['Q_mean'].values.mean(axis=0)
            avg_Qb  = ds['Qb_mean'].values.mean(axis=0)

            lat_values = ds['latitude'].values
            lon_values = convert_longitudes(ds['longitude'].values)
            ds.close()

            # Build flat arrays via meshgrid instead of nested loops
            lats, lons = np.meshgrid(lat_values, lon_values, indexing='ij')
            df = pd.DataFrame({
                'Date':    pd.Timestamp(year=year, month=month, day=1),
                'lat':     lats.ravel(),
                'lon':     lons.ravel(),
                'avg_ELD': avg_ELD.ravel(),
                'avg_Q':   avg_Q.ravel(),
                'avg_Qb':  avg_Qb.ravel(),
            })

            # Build the grid→country lookup once; reuse for every subsequent file
            if grid_to_country is None:
                print("Building grid-to-country lookup (once)...")
                gdf_grid = gpd.GeoDataFrame(
                    df[['lat', 'lon']],
                    geometry=gpd.points_from_xy(df['lon'], df['lat']),
                    crs=countries.crs,
                )
                joined = gpd.sjoin(
                    gdf_grid,
                    countries[['Country', 'geometry']],
                    how='left',
                    predicate='intersects',
                )
                grid_to_country = joined[['lat', 'lon', 'Country']].copy()

            df = df.merge(grid_to_country, on=['lat', 'lon'], how='left')

            monitor_memory(step=f"processing {year}-{month:02d}")

            #country_avg = (
            #    df.groupby(['Date', 'Country'])[['avg_ELD', 'avg_Q', 'avg_Qb']]
            #    .mean()
            #    .reset_index()
            #)
            country_avg = (
                df.groupby(['Date', 'Country'])[['avg_ELD', 'avg_Q', 'avg_Qb']]
                .agg(eld_sum_avg=('avg_ELD', 'mean'), eld_sum_sum=('avg_ELD', 'sum'), avg_Q=('avg_Q', 'mean'), avg_Qb=('avg_Qb', 'mean'),)
                .reset_index()
            )

            year_results.append(country_avg)


            print(year, ':', month, ' (', time.time() - start_time, ')')

    final_year_results = pd.concat(year_results, ignore_index=True)
    final_year_results.to_csv(f'/dx03/data/cockburn_era5/monthly_ELD_sum_{year}.csv', index=False)
    print(f'saved results for {year}!')

print('All files saved!')
