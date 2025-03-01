#!/usr/bin/env python
"""
AWS Level 0 (L0) to Level 1 (L1) data processing
"""
import numpy as np
import pandas as pd
import xarray as xr
import re


def toL1(L0, vars_df, flag_file=None, T_0=273.15, tilt_threshold=-100):
    '''Process one Level 0 (L0) product to Level 1

    Parameters
    ----------
    L0 : xarray.Dataset
        Level 0 dataset
    vars_df : pd.DataFrame
        Metadata dataframe
    flag_file : str
        Flag .csv file path for bad data
    T_0 : int
        Air temperature for sonic ranger adjustment
    tilt_threshold : int
        Tilt-o-meter threshold for valid measurements
        
    Returns
    -------
    ds : xarray.Dataset
        Level 1 dataset
    '''
    assert(type(L0) == xr.Dataset)
    ds = L0

    for l in list(ds.keys()):
        if l not in ['time', 'msg_i', 'gps_lat', 'gps_lon', 'gps_alt', 'gps_time']:
            ds[l] = _reformatArray(ds[l])

    # ds['time_orig'] = ds['time'] # Not used

    # The following drops duplicate datetime indices. Needs to run before _addTimeShift!
    # We can optionally also drop duplicates within _addTimeShift using pandas duplicated,
    # but retaining the following code instead to preserve previous methods. PJW
    _, index = np.unique(ds['time'], return_index=True)
    ds = ds.isel(time=index)

    # If we do not want to shift hourly average values back -1 hr, then comment the following line.
    ds = addTimeShift(ds, vars_df)

    if hasattr(ds, 'dsr_eng_coef'): 
        ds['dsr'] = (ds['dsr'] * 10) / ds.attrs['dsr_eng_coef']                # Convert radiation from engineering to physical units
    if hasattr(ds, 'usr_eng_coef'):                                            # TODO add metadata to indicate whether radiometer values are corrected with calibration values or not
        ds['usr'] = (ds['usr'] * 10) / ds.attrs['usr_eng_coef']
    if hasattr(ds, 'dlr_eng_coef'):
        ds['dlr'] = ((ds['dlr'] * 10) / ds.attrs['dlr_eng_coef']) + 5.67E-8*(ds['t_rad'] + T_0)**4
    if hasattr(ds, 'ulr_eng_coef'):
        ds['ulr'] = ((ds['ulr'] * 10) / ds.attrs['ulr_eng_coef']) + 5.67E-8*(ds['t_rad'] + T_0)**4

    ds['z_boom_u'] = _reformatArray(ds['z_boom_u'])                            # Reformat boom height
    ds['z_boom_u'] = ds['z_boom_u'] * ((ds['t_u'] + T_0)/T_0)**0.5             # Adjust sonic ranger readings for sensitivity to air temperature       
    
    if ds['gps_lat'].dtype.kind == 'O':                                        # Decode and reformat GPS information
        if 'NH' in ds['gps_lat'].dropna(dim='time').values[1]:
            ds = decodeGPS(ds, ['gps_lat','gps_lon','gps_time'])
        else:
            try:
                ds = decodeGPS(ds, ['gps_lat','gps_lon','gps_time'])          # TODO this is a work around specifically for L0 RAW processing for THU_U. Find a way to make this slicker
            except:
                print('Invalid GPS type {ds["gps_lat"].dtype} for decoding')
            
    for l in ['gps_lat', 'gps_lon', 'gps_alt','gps_time']:
        ds[l] = _reformatArray(ds[l])  

    if hasattr(ds, 'latitude') and hasattr(ds, 'longitude'):
        ds['gps_lat'] = reformatGPS(ds['gps_lat'], ds.attrs['latitude'])
        ds['gps_lon'] = reformatGPS(ds['gps_lon'], ds.attrs['longitude'])

    if hasattr(ds, 'logger_type'):                                             # Convert tilt voltage to degrees
        if ds.attrs['logger_type'].upper() == 'CR1000':                    
            ds['tilt_x']  = getTiltDegrees(ds['tilt_x'], tilt_threshold) 
            ds['tilt_y'] = getTiltDegrees(ds['tilt_y'], tilt_threshold)  
            
    if hasattr(ds, 'tilt_y_factor'):                                           # Apply tilt factor (e.g. -1 will invert tilt angle)
        ds['tilt_y'] = ds['tilt_y']*ds.attrs['tilt_y_factor']

    # Smooth everything
    # Note that this should be OK for CR1000 tx (data only every 6 hrs),
    # since we interpolate above in _getTiltDegrees. PJW
    ds['tilt_x']  = smoothTilt(ds['tilt_x'], 7)                                # Smooth tilt
    ds['tilt_y']  = smoothTilt(ds['tilt_y'], 7)                               
    
    if hasattr(ds, 'bedrock'):                                                 # Fix tilt to zero if station is on bedrock
        if ds.attrs['bedrock']==True or ds.attrs['bedrock'].lower() in 'true':
            ds['tilt_x'] = (('time'), np.arange(ds['time'].size)*0)
            ds['tilt_y'] = (('time'), np.arange(ds['time'].size)*0)
            
    ds['wdir_u'] = ds['wdir_u'].where(ds['wspd_u'] != 0)                       # Get directional wind speed                    
    ds['wspd_x_u'], ds['wspd_y_u'] = calcWindDir(ds['wspd_u'], ds['wdir_u']) 
    
    if ds.attrs['number_of_booms']==1:                                         # 1-boom processing
        if ~ds['z_pt'].isnull().all():                                         # Calculate pressure transducer fluid density                                           
            if hasattr(ds, 'pt_z_offset'):                                     # Apply SR50 stake offset
                ds['z_pt'] = ds['z_pt'] + int(ds.attrs['pt_z_offset'])              
            ds['z_pt_cor'],ds['z_pt']=getPressDepth(ds['z_pt'], ds['p_u'], 
                                                    ds.attrs['pt_antifreeze'], 
                                                    ds.attrs['pt_z_factor'], 
                                                    ds.attrs['pt_z_coef'], 
                                                    ds.attrs['pt_z_p_coef'])       
            
    elif ds.attrs['number_of_booms']==2:                                       # 2-boom processing
        ds['z_boom_l'] = _reformatArray(ds['z_boom_l'])                        # Reformat boom height    
        ds['z_boom_l'] = ds['z_boom_l'] * ((ds['t_l'] + T_0)/T_0)**0.5         # Adjust sonic ranger readings for sensitivity to air temperature
        ds['wdir_l'] = ds['wdir_l'].where(ds['wspd_l'] != 0)                   # Get directional wind speed    
        ds['wspd_x_l'], ds['wspd_y_l'] = calcWindDir(ds['wspd_l'], ds['wdir_l'])
     
    if hasattr(ds, 'wdir_i'):    
        if ~ds['wdir_i'].isnull().all() and ~ds['wspd_i'].isnull().all():      # Instantaneous msg processing
            ds['wdir_i'] = ds['wdir_i'].where(ds['wspd_i'] != 0)               # Get directional wind speed                    
            ds['wspd_x_i'], ds['wspd_y_i'] = calcWindDir(ds['wspd_i'], ds['wdir_i'])   
    return ds

def addTimeShift(ds, vars_df):
    '''Shift times based on file format and logger type (shifting only hourly averaged values,
    and not instantaneous variables). For raw (10 min), all values are sampled instantaneously
    so do not shift. For STM (1 hour), values are averaged and assigned to end-of-hour by the
    logger, so shift by -1 hr. For TX (time frequency depends on v2 or v3) then time is shifted
    depending on logger type. We use the 'instantaneous_hourly' boolean from variables.csv to
    determine if a variable is considered instantaneous at hourly samples.

    This approach creates two separate sub-dataframes, one for hourly-averaged variables
    and another for instantaneous variables. The instantaneous dataframe should never be
    shifted. We apply shifting only to the hourly average dataframe, then concat the two
    dataframes back together.

    It is possible to use pandas merge or join instead of concat, there are equivalent methods
    in each. In this case, we use concat throughout.

    Fausto et al. 2021 specifies the convention of assigning hourly averages to start-of-hour,
    so we need to retain this unless clearly communicated to users.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset to apply time shift to
    vars_df : pd.DataFrame
        Metadata dataframe

    Returns
    -------
    ds_out : xarray.Dataset
        Dataset with shifted times
    '''
    df = ds.to_dataframe()
    # No need to drop duplicates here if performed prior to calling this function.
    # df = df[~df.index.duplicated(keep='first')] # drop duplicates, keep=first is arbitrary
    df['doy'] = df.index.dayofyear
    i_cols = [x for x in df.columns if x in vars_df.index and vars_df['instantaneous_hourly'][x] is True] # instantaneous only, list of columns
    df_i = df.filter(items=i_cols, axis=1) # instantaneous only dataframe
    df_a = df.drop(df_i.columns, axis=1) # hourly ave dataframe

    if ds.attrs['format'] == 'raw':
        # 10-minute data, no shifting
        df_out = df
    elif ds.attrs['format'] == 'STM':
        # hourly-averaged, non-transmitted
        # shift everything except instantaneous, any logger type
        df_a = df_a.shift(periods=-1, freq="H")
        df_out = pd.concat([df_a, df_i], axis=1) # different columns, same datetime indices
    elif ds.attrs['format'] == 'TX':
        if ds.attrs['logger_type'] == 'CR1000X':
            # v3, data is hourly all year long
            # shift everything except instantaneous
            df_a = df_a.shift(periods=-1, freq="H")
            df_out = pd.concat([df_a, df_i], axis=1) # different columns, same datetime indices
        elif ds.attrs['logger_type'] == 'CR1000':
            # v2, data is hourly (6-hr for instantaneous) for DOY 100-300, otherwise daily at 00 UTC
            # shift non-instantaneous hourly for DOY 100-300, else do not shift daily
            df_a_hourly = df_a.loc[(df_a['doy'] >= 100) & (df_a['doy'] <= 300)]
            # df_a_hourly = df_a.loc[df_a['doy'].between(100, 300, inclusive='both')] # equivalent to above
            df_a_daily_1 = df_a.loc[(df_a['doy'] < 100)]
            df_a_daily_2 = df_a.loc[(df_a['doy'] > 300)]

            # shift the hourly ave data
            df_a_hourly = df_a_hourly.shift(periods=-1, freq="H")

            # stitch everything back together
            df_concat_u = pd.concat([df_a_daily_1, df_a_daily_2, df_a_hourly], axis=0) # same columns, different datetime indices
            # It's now possible for df_concat_u to have duplicate datetime indices
            df_concat_u = df_concat_u[~df_concat_u.index.duplicated(keep='first')] # drop duplicates, keep=first is arbitrary

            df_out = pd.concat([df_concat_u, df_i], axis=1) # different columns, same datetime indices
            df_out = df_out.sort_index()

    # Back to xarray, and re-assign the original attrs
    df_out = df_out.drop('doy', axis=1)
    ds_out = df_out.to_xarray()
    ds_out = ds_out.assign_attrs(ds.attrs) # Dataset attrs
    for x in ds_out.data_vars: # variable-specific attrs
        ds_out[x].attrs = ds[x].attrs

    # equivalent to above:
    # vals = [xr.DataArray(data=df_out[c], dims=['time'], coords={'time':df_out.index}, attrs=ds[c].attrs) for c in df_out.columns]
    # ds_out = xr.Dataset(dict(zip(df_out.columns, vals)), attrs=ds.attrs)
    return ds_out

def getPressDepth(z_pt, p, pt_antifreeze, pt_z_factor, pt_z_coef, pt_z_p_coef): 
    '''Adjust pressure depth and calculate pressure transducer depth based on 
    pressure transducer fluid density
    
    Parameters
    ----------
    z_pt : xr.Dataarray
        Pressure transducer height (corrected for offset)
    p : xr.Dataarray
        Air pressure
    pt_antifreeze : float
        Pressure transducer anti-freeze percentage for fluid density 
        correction
    pt_z_factor : float
        Pressure transducer factor
    pt_z_coef : float
        Pressure transducer coefficient
    pt_z_p_coef : float
        Pressure transducer coefficient
    
    Returns
    -------
    z_pt_cor : xr.Dataarray
        Pressure transducer height corrected
    z_pt : xr.Dataarray
        Pressure transducer depth
    '''
    # Calculate pressure transducer fluid density                                        
    if pt_antifreeze == 50:                                                    #TODO: Implement function w/ reference (analytical or from LUT)                                             
        rho_af = 1092                                                          #TODO: Track uncertainty
    elif pt_antifreeze == 100:
        rho_af = 1145
    else:
        rho_af = np.nan
        print('ERROR: Incorrect metadata: "pt_antifreeze" = ' +
              f'{pt_antifreeze}. Antifreeze mix only supported at 50% or 100%')
        # assert(False)
                
    # Correct pressure depth
    z_pt_cor = z_pt * pt_z_coef * pt_z_factor * 998.0 / rho_af + 100 * (pt_z_p_coef - p) / (rho_af * 9.81)

    # Calculate pressure transducer depth
    z_pt = z_pt * pt_z_coef * pt_z_factor * 998.0 / rho_af
    
    return z_pt_cor, z_pt

def smoothTilt(tilt, win_size):
    '''Smooth tilt values using a rolling window. This is translated from the
    previous IDL/GDL smoothing algorithm:
    tiltX = smooth(tiltX,7,/EDGE_MIRROR,MISSING=-999) & tiltY = smooth(tiltY,7,/EDGE_MIRROR, MISSING=-999)
    endif
    In Python, this should be
    dstxy = dstxy.rolling(time=7, win_type='boxcar', center=True).mean()
    But the EDGE_MIRROR makes it a bit more complicated
    
    Parameters
    ----------
    tilt : xarray.DataArray
        Array (either 'tilt_x' or 'tilt_y'), tilt values (can be in degrees or voltage)
    win_size : int
        Window size to use in pandas 'rolling' method.
        e.g. a value of 7 spans 70 minutes using 10 minute data.

    Returns
    -------
    tdf_rolling : tuple, as: (str, numpy.ndarray)
        The numpy array is the tilt values, smoothed with a rolling mean
    '''
    s = int(win_size/2)
    tdf = tilt.to_dataframe()
    mirror_start = tdf.iloc[:s][::-1]
    mirror_end = tdf.iloc[-s:][::-1]
    mirrored_tdf = pd.concat([mirror_start, tdf, mirror_end])

    tdf_rolling = (
        ('time'),
        mirrored_tdf.rolling(
            win_size, win_type='boxcar', min_periods=1, center=True
            ).mean()[s:-s].values.flatten()
        )
    return tdf_rolling

def getTiltDegrees(tilt, threshold):
    '''Filter tilt with given threshold, and convert from voltage to degrees. 
    Voltage-to-degrees converseion is based on the equation in 3.2.9 at 
    https://essd.copernicus.org/articles/13/3819/2021/#section3    

    Parameters
    ----------
    tilt : xarray.DataArray
        Array (either 'tilt_x' or 'tilt_y'), tilt values (voltage)
    threshold : int
        Values below this threshold (-100) will not be retained.
    
    Returns
    -------
    dst.interpolate_na() : xarray.DataArray
        Array (either 'tilt_x' or 'tilt_y'), tilt values (degrees)
    '''
    # notOKtiltX = where(tiltX lt -100, complement=OKtiltX) & notOKtiltY = where(tiltY lt -100, complement=OKtiltY)
    notOKtilt = (tilt < threshold)
    OKtilt = (tilt >= threshold)
    tilt = tilt / 10
    
    # IDL version:
    # tiltX = tiltX/10.
    # tiltnonzero = where(tiltX ne 0 and tiltX gt -40 and tiltX lt 40)
    # if n_elements(tiltnonzero) ne 1 then tiltX[tiltnonzero] = tiltX[tiltnonzero]/abs(tiltX[tiltnonzero])*(-0.49*(abs(tiltX[tiltnonzero]))^4 + 3.6*(abs(tiltX[tiltnonzero]))^3 - 10.4*(abs(tiltX[tiltnonzero]))^2 +21.1*(abs(tiltX[tiltnonzero])))
    # tiltY = tiltY/10.
    # tiltnonzero = where(tiltY ne 0 and tiltY gt -40 and tiltY lt 40)
    # if n_elements(tiltnonzero) ne 1 then tiltY[tiltnonzero] = tiltY[tiltnonzero]/abs(tiltY[tiltnonzero])*(-0.49*(abs(tiltY[tiltnonzero]))^4 + 3.6*(abs(tiltY[tiltnonzero]))^3 - 10.4*(abs(tiltY[tiltnonzero]))^2 +21.1*(abs(tiltY[tiltnonzero])))
    
    dst = tilt
    nz = (dst != 0) & (np.abs(dst) < 40)
    
    dst = dst.where(~nz, other = dst / np.abs(dst)
                      * (-0.49
                         * (np.abs(dst))**4 + 3.6
                         * (np.abs(dst))**3 - 10.4
                         * (np.abs(dst))**2 + 21.1
                         * (np.abs(dst))))
    
    # if n_elements(OKtiltX) gt 1 then tiltX[notOKtiltX] = interpol(tiltX[OKtiltX],OKtiltX,notOKtiltX) ; Interpolate over gaps for radiation correction; set to -999 again below.
    dst = dst.where(~notOKtilt)
    return dst.interpolate_na(dim='time', use_coordinate=False)                #TODO: Filling w/o considering time gaps to re-create IDL/GDL outputs. Should fill with coordinate not False. Also consider 'max_gap' option?

def calcWindDir(wspd, wdir, deg2rad=np.pi/180):
    '''Calculate directional wind speed from wind speed and direction
    
    Parameters
    ----------
    wspd : xr.Dataarray
        Wind speed data array
    wdir : xr.Dataarray
        Wind direction data array
    deg2rad : float
        Degree to radians coefficient. The default is np.pi/180
    
    Returns
    -------
    wspd_x : xr.Dataarray
        Wind speed in X direction
    wspd_y : xr.Datarray
        Wind speed in Y direction
    '''        
    wspd_x = wspd * np.sin(wdir * deg2rad)
    wspd_y = wspd * np.cos(wdir * deg2rad) 
    return wspd_x, wspd_y
    
def decodeGPS(ds, gps_names):
    '''Decode GPS information based on names of GPS attributes. This should be 
    applied if gps information does not consist of float values
    
    Parameters
    ----------
    ds : xr.Dataset
        Data set
    gps_names : list
        Variable names for GPS information, such as "gps_lat", "gps_lon" and
        "gps_alt"
    
    Returns
    -------
    ds : xr.Dataset
        Data set with decoded GPS information
    '''
    for v in gps_names:
        a = ds[v].attrs    
        str2nums = [re.findall(r"[-+]?\d*\.\d+|\d+", _) if isinstance(_, str) else [np.nan] for _ in ds[v].values]
        ds[v][:] = pd.DataFrame(str2nums).astype(float).T.values[0]
        ds[v] = ds[v].astype(float)
        ds[v].attrs = a 
    return ds

def reformatGPS(pos_arr, attrs):
    '''Correct position if only recorded minutes (and not degrees), and 
    reformat values and attributes
    
    Parameters
    ----------
    pos_arr : xr.Dataarray
        GPS position array
    attrs : dict
        Array attributes
    
    Returns
    -------
    pos_arr : xr.Dataarray
        Formatted GPS position array
    '''       
    if np.any((pos_arr <= 90) & (pos_arr > 0)):  
        pos_arr = pos_arr + 100*attrs
    a = pos_arr.attrs                                                     
    pos_arr = np.floor(pos_arr / 100) + (pos_arr / 100 - np.floor(pos_arr / 100)) * 100 / 60
    pos_arr.attrs = a 
    return pos_arr 

def _reformatArray(ds_arr):
    '''Reformat DataArray values and attributes
    
    Parameters
    ----------
    ds_arr : xr.Dataarray
        Data array
    
    Returns
    -------
    ds_arr : xr.Dataarray
        Formatted data array
    '''
    a = ds_arr.attrs                                                           # Store
    ds_arr.values = pd.to_numeric(ds_arr, errors='coerce')
    ds_arr.attrs = a                                                           # Reformat
    return ds_arr         

def _removeVars(ds, v_names):
    '''Remove redundant variables if present in dataset
    
    Parameters
    ----------
    ds : xr.Dataset
        Data set
    v_names : list
        List of column names to drop
    
    Returns
    -------
    ds : xr.Dataset
        Data set with removed variables
    '''
    for v in v_names:
        if v in list(ds.variables): ds = ds.drop_vars(v)
    return ds

def _popCols(ds, booms, data_type, vars_df, cols):
    '''Populate data array columns with given variable names from look-up table
    
    Parameters
    ----------
    ds : xr.Dataset
        Data set
    booms : int
        Number of booms (1 or 2)
    data_type : str
        Type of data ("tx", "raw")
    vars_df : pd.DataFrame
        Variables lookup table
    cols : list
        Names of columns to populate
    
    Returns
    -------
    ds : xr.Dataset
        Data with populated columns
    '''
    if booms==1:
        names = vars_df.loc[(vars_df[cols[0]]!='two-boom')]

    elif booms==2:
        names = vars_df.loc[(vars_df[cols[0]]!='one-boom')]
       
    for v in list(names.index):
        if v not in list(ds.variables):
            ds[v] = (('time'), np.arange(ds['time'].size)*np.nan)      
    return ds

# def _popCols(ds, booms, data_type, vars_df, cols):
#     if booms==1:
#         if data_type !='TX':
#             names = vars_df.loc[(vars_df[cols[0]]!='two-boom')]
#         else:
#             names = vars_df.loc[(vars_df[cols[0]] != 'two-boom') & vars_df[cols[1]] != 'tx']
    
#     elif booms==2:
#         if data_type !='TX':
#             names = vars_df.loc[(vars_df[cols[0]]!='two-boom')]
#         else:
#             names = vars_df.loc[(vars_df[cols[0]] != 'two-boom') & vars_df[cols[1]] != 'tx']
       
#     for v in list(names.index):
#         if v not in list(ds.variables):
#             ds[v] = (('time'), np.arange(ds['time'].size)*np.nan)      
#     return ds

#------------------------------------------------------------------------------

if __name__ == "__main__": 
    # unittest.main() 
    pass    
