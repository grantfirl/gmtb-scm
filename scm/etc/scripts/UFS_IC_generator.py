#!/usr/bin/env python

import argparse
import os
import fnmatch
import logging
from netCDF4 import Dataset
import numpy as np
from shapely.geometry import Point, Polygon
import copy
import math
import f90nml
import re
import fv3_remap
from pandas import *

###############################################################################
# Global settings                                                             #
###############################################################################

#Physical constants
earth_radius = 6371000.0 #m
rdgas        = 287.05
rvgas        = 461.50
cp           = 1004.6
zvir         = rvgas/rdgas - 1.
rocp         = rdgas/cp
grav         = 9.80665
deg_to_rad   = math.pi/180.0
kappa        = rdgas/cp
p0           = 100000.0

missing_value = 9.99e20

# Path to the directory containing processed case input files
PROCESSED_CASE_DIR = '../../data/processed_case_input'

# Path to the directory containing NoahMP table files (need MPTABLE.TBL and SOILPARM.TBL)
NOAHMP_TABLES_DIR = '../../data/raw_case_input/NoahMP_tables'

# For developers: set logging level to DEBUG for additional output
#LOGLEVEL = logging.DEBUG
LOGLEVEL = logging.INFO

###############################################################################
# Command line arguments                                                      #
###############################################################################

parser = argparse.ArgumentParser()
group1 = parser.add_mutually_exclusive_group(required=True)
group1.add_argument('-l', '--location',   help='longitude and latitude in degress E and N, respectively, separated by a space', nargs=2, type=float)
group1.add_argument('-ij','--index',      help='i,j indices within the tile (if known - bypasses search for closest model point to lon/lat location)', nargs=2, type=int)
parser.add_argument('-d', '--date',       help='date corresponding to initial conditions in YYYYMMDDHHMM format', required=True)
parser.add_argument('-i', '--in_dir',     help='input directory path containing FV3 input files', required=True)
parser.add_argument('-g', '--grid_dir',   help='directory path containing FV3 tile supergrid files', required=True)
parser.add_argument('-f', '--forcing_dir',help='directory path containing physics diag files', required=True)
parser.add_argument('-t', '--tile',       help='tile of desired point (if known - bypasses tile search if present)', type=int, choices=range(1,7))
parser.add_argument('-a', '--area',       help='area of grid cell in m^2', type=float)
parser.add_argument('-mp','--noahmp',     help='flag to generate cold-start ICs for NoahMP LSM from Noah LSM ICs', action='store_true')
parser.add_argument('-n', '--case_name',  help='name of case', required=True)
parser.add_argument('-oc','--old_chgres', help='flag to denote that the initial conditions use an older data format (pre-chgres_cube)', action='store_true')

###############################################################################
# Functions and subroutines                                                   #
###############################################################################

def parse_arguments():
    """Parse command line arguments"""
    args = parser.parse_args()
    location = args.location
    index = args.index
    date = args.date
    in_dir = args.in_dir
    grid_dir = args.grid_dir
    forcing_dir = args.forcing_dir
    tile = args.tile
    area = args.area
    case_name = args.case_name
    noahmp = args.noahmp
    old_chgres = args.old_chgres
    
    #validate args
    if not os.path.exists(in_dir):
        message = 'The directory {0} does not exist'.format(in_dir)
        logging.critical(message)
        raise Exception(message)
    
    if not index:
        if not 0 <= location[0] <= 360 :
            message = 'The longitude {0} is outside of the range {1}'.format(location[0], '[0,360]')
            logging.critical(message)
            raise Exception(message)
        
        if not -90 <= location[1] <= 90:
            message = 'The latitude {0} is outside of the range {1}'.format(location[1], '[-90,90]')
            logging.critical(message)
            raise Exception(message)
    
    date_dict = {}
    if len(date) != 12:
        message = 'The entered date {0} does not have the 12 characters expected in the format YYYYMMDDHHMM'.format(date)
        logging.critical(message)
        raise Exception(message)
    else:
        date_dict["year"] = np.int(date[0:4])
        date_dict["month"] = np.int(date[4:6])
        date_dict["day"] = np.int(date[6:8])
        date_dict["hour"] = np.int(date[8:10])
        date_dict["minute"] = np.int(date[10:])
        
    return (location, index, date_dict, in_dir, grid_dir, forcing_dir, tile, area, noahmp, case_name, old_chgres)

def setup_logging():
    """Sets up the logging module."""
    logging.basicConfig(format='%(levelname)s: %(message)s', level=LOGLEVEL)
    
def find_tile(loc, dir):
    """Find the FV3 tile with the given lon/lat"""
    #returns the integer tile number
    
    # should be looking in the directory with supergrid data (probably "fix" directory)
    filename_pattern = '*grid.tile*.nc'
    
    #find all supergrid files in the directory
    grid_fnames = []
    for f_name in os.listdir(dir):
       if fnmatch.fnmatch(f_name, filename_pattern):
          grid_fnames.append(f_name)
    if not grid_fnames:
        message = 'No filenames matching the pattern {0} found in {1}'.format(filename_pattern,dir)
        logging.critical(message)
        raise Exception(message)
    
    #non-polar tiles can use traditional 2D point-in-polygon methods; if a point is not in a non-polar tile,
    #it is in one of the polar tiles, and the tile can be distinguished by the sign of latitude of the point
    polar_tile_filenames = []
    found_tile = False
    for f_name in grid_fnames:
        if not found_tile:
            nc_file = Dataset('{0}/{1}'.format(dir,f_name))
            longitude = np.array(nc_file['x']).swapaxes(0,1)
            latitude = np.array(nc_file['y']).swapaxes(0,1)
            nc_file.close()
            
            adj_long = False        
            #look for reversal of longitude; if found, adjust longitude so that 0-360 transition doesn't exist
            for row in longitude:
                if not (np.all(np.diff(row) >= 0) or np.all(np.diff(row) <= 0)):
                    adj_long = True
            if adj_long:
                longitude[longitude < 180] += 360
            
            #get lon/lat pairs for all edges of the tiles
            
            edge_1_lon = longitude[0,:]
            edge_1_lat = latitude[0,:]
            edge_1 = zip(edge_1_lon, edge_1_lat)
                        
            edge_2_lon = longitude[:,-1]
            edge_2_lat = latitude[:,-1]
            edge_2 = zip(edge_2_lon, edge_2_lat)
                        
            edge_3_lon = longitude[-1,:]
            edge_3_lat = latitude[-1,:]
            edge_3 = zip(edge_3_lon, edge_3_lat)
            edge_3.reverse() #need to reverse the direction of this edge to form a regular polygon
            
            edge_4_lon = longitude[:,0]
            edge_4_lat = latitude[:,0]
            edge_4 = zip(edge_4_lon, edge_4_lat)
            edge_4.reverse() #need to reverse the direction of this edge to form a regular polygon
                        
            polygon_points = edge_1 + edge_2 + edge_3 + edge_4
                        
            tile_polygon = Polygon(polygon_points)
            tile_polygon = tile_polygon.simplify(0)
            
            if tile_polygon.is_valid:  #this will be True unless the tile is a polar tile, which will not form a regular polygon in Cartesian space using lon/lat data
                temp_loc = copy.deepcopy(loc)
                if adj_long:
                    if loc[0] < 180:
                        temp_loc[0] += 360
                loc_point = Point(temp_loc)
                if tile_polygon.contains(loc_point):
                    found_tile = True
                    return f_name.split('tile')[1].split('.nc')[0] 
            else:
                polar_tile_filenames.append(f_name)
                
    #if the tile hasn't been found by this point, it must be contained within a polar tile
    for f_name in polar_tile_filenames:
        nc_file = Dataset('{0}/{1}'.format(dir,f_name))
        latitude = np.array(nc_file['y']).swapaxes(0,1)
        nc_file.close()
        
        #if the sign of the mean latitude of the tile is the same as that of the point, the tile has been found
        if np.sign(np.mean(latitude)) == np.sign(loc[1]):
            found_tile = True
            return f_name.split('tile')[1].split('.nc')[0]        
    return -1

def find_loc_indices(loc, dir, tile):
    """Find the nearest neighbor FV3 grid point given a lon/lat pair and the tile number"""
    #returns the indices of the nearest neighbor point in the given tile, the lon/lat of the nearest neighbor, 
    #and the distance (m) from the given point to the nearest neighbor grid cell
    
    filename_pattern = '*grid.tile{0}.nc'.format(tile)
    for f_name in os.listdir(dir):
       if fnmatch.fnmatch(f_name, filename_pattern):
          filename = f_name
    if not filename:
        message = 'No filenames matching the pattern {0} found in {1}'.format(filename_pattern,dir)
        logging.critical(message)
        raise Exception(message)
    
    nc_file = Dataset('{0}/{1}'.format(dir,filename))
    #read in supergrid longitude and latitude
    lon_super = np.array(nc_file['x']).swapaxes(0,1)   #[lat,lon] or [y,x]   #
    lat_super = np.array(nc_file['y']).swapaxes(0,1)    #[lat,lon] or [y,x]   #
    #get the longitude and latitude data for the grid centers by slicing the supergrid 
    #and taking only odd-indexed values
    longitude = lon_super[1::2,1::2]
    latitude = lat_super[1::2,1::2]
    nc_file.close()
    
    adj_long = False        
    #look for reversal of longitude; if found, adjust longitude so that 0-360 transition doesn't exist
    temp_loc = copy.deepcopy(loc)
    for row in longitude:
        if not (np.all(np.diff(row) >= 0) or np.all(np.diff(row) <= 0)):
            adj_long = True
    if adj_long:
        longitude[longitude < 180] += 360
        if loc[0] < 180:
            temp_loc[0] += 360
    
    #set up an array to hold the euclidean distance between the given point and every grid cell
    eucl_dist = np.zeros((longitude.shape[0],longitude.shape[1]))
    
    #get the Cartesian location of the given point
    cart_loc = np.array(sph2cart(math.radians(temp_loc[0]), math.radians(temp_loc[1]), earth_radius))
    
    for i in range(len(longitude)):
        for j in range(len(longitude[i])):
            #get the Cartesian location of all grid points
            cart_cell = np.array(sph2cart(math.radians(longitude[i,j]), math.radians(latitude[i,j]), earth_radius))
            
            #calculate the euclidean distance from the given point to the current grid cell
            eucl_dist[i,j] = np.linalg.norm(cart_loc - cart_cell)
    
    #get the indices of the grid point with the minimum euclidean distance to the given point
    i,j = np.unravel_index(eucl_dist.argmin(), eucl_dist.shape)
    
    #print i,j,longitude[i,j]%360.0, latitude[i,j], eucl_dist[i,j]
    #exit()
    
    return (i,j,longitude[i,j]%360.0, latitude[i,j], eucl_dist[i,j])

def find_lon_lat_of_indices(indices, dir, tile):
    """Find the longitude and latitude of the given indices within the given tile."""
    
    filename_pattern = '*grid.tile{0}.nc'.format(tile)
    for f_name in os.listdir(dir):
       if fnmatch.fnmatch(f_name, filename_pattern):
          filename = f_name
    if not filename:
        message = 'No filenames matching the pattern {0} found in {1}'.format(filename_pattern,dir)
        logging.critical(message)
        raise Exception(message)
    
    nc_file = Dataset('{0}/{1}'.format(dir,filename))
    #read in supergrid longitude and latitude
    lon_super = np.array(nc_file['x']).swapaxes(0,1)   #[lat,lon] or [y,x]   #
    lat_super = np.array(nc_file['y']).swapaxes(0,1)    #[lat,lon] or [y,x]   #
    #get the longitude and latitude data for the grid centers by slicing the supergrid 
    #and taking only odd-indexed values
    longitude = lon_super[1::2,1::2]
    latitude = lat_super[1::2,1::2]
    nc_file.close()
    
    return (longitude[indices[0],indices[1]], latitude[indices[0],indices[1]])
    
def sph2cart(az, el, r):
    """Calculate the Cartesian coordiates from spherical coordinates"""
    
    rcos_theta = r * np.cos(el)
    x = rcos_theta * np.cos(az)
    y = rcos_theta * np.sin(az)
    z = r * np.sin(el)
    
    return (x, y, z)    

def get_UFS_IC_data(dir, forcing_dir, tile, i, j, old_chgres):
    """Get the state, surface, and orographic data for the given tile and indices"""
    #returns dictionaries with the data
    
    vgrid_data = get_UFS_vgrid_data(dir) #reads gfs_ctrl.nc (has vertical levels)
    state_data = get_UFS_state_data(vgrid_data, dir, forcing_dir, tile, i, j, old_chgres)
    surface_data = get_UFS_surface_data(dir, tile, i, j, old_chgres)
    oro_data = get_UFS_oro_data(dir, tile, i, j)
    
    # #calculate derived quantities
    # if old_chgres:
    #     #temperature
    #     nlevs = state_data["nlevs"]
    #     gz=state_data["z"]*grav
    #     pn1=np.zeros([nlevs+1])
    #     temp=np.zeros([nlevs])
    #     for k in range(nlevs+1):
    #       pn1[k]=np.log(vgrid_data["ak"][k]+state_data["p_surf"]*vgrid_data["bk"][k])
    #     for k in range(nlevs):
    #       temp[k] = (gz[k]-gz[k+1])/( rdgas*(pn1[k+1]-pn1[k])*(1.+zvir*state_data["qv"][k]) )
    #     state_data["T"] = temp
    #     state_data["pres"] = np.exp(pn1[0:nlevs])
    
    #print "qv = ",state_data["qv"]
    #print len(state_data["qv"])
    
    return (state_data, surface_data, oro_data)
    
def get_UFS_state_data(vgrid, dir, forcing_dir, tile, i, j, old_chgres):
    """Get the state data for the given tile and indices"""
    
    filename_pattern = '*grid.tile*.nc'
    
    #find all supergrid files in the directory
    grid_fnames = []
    for f_name in os.listdir(dir):
       if fnmatch.fnmatch(f_name, filename_pattern):
          grid_fnames.append(f_name)
    if not grid_fnames:
        message = 'No filenames matching the pattern {0} found in {1}'.format(filename_pattern,dir)
        logging.critical(message)
        raise Exception(message)
    
    for f_name in grid_fnames:
        nc_file = Dataset('{0}/{1}'.format(dir,f_name))
        lon_super = np.array(nc_file['x']).swapaxes(0,1)
        lat_super = np.array(nc_file['y']).swapaxes(0,1)
        nc_file.close()
        stride = 32
        lon_super_reduced = lon_super[0::stride,0::stride]
        lat_super_reduced = lat_super[0::stride,0::stride]
        #print f_name
        #print DataFrame(lon_super_reduced)
        #print DataFrame(lat_super_reduced)
        
        #for i in range(0, lon_super_reduced.shape[0]):
        #    print i, lon_super_reduced[i,:]
        #print lon_super_reduced
        #print lat_super_reduced
        #for j in range(0, longitude.shape[0]):
        #    for i in range(0, longitude.shape[1]):
        #        print longitude[j,i]
        
    
    
    nc_file_data = Dataset('{0}/{1}'.format(dir,'gfs_data.tile{0}.nc'.format(tile)))
    
    #the majority of this routine is from Phil Pegion (NOAA PSD)
    
    # get nlevs from the gfs_ctrl.nc data
    nlevs_model=vgrid["nlevs"]
    
    # upper air fields from initial conditions (all data are top-first)
    zh_rev=nc_file_data['zh'][:,j,i]
    sphum_rev=nc_file_data['sphum'][:,j,i]
    # o3 and qv are taken from ics. 
    o3_rev=nc_file_data['o3mr'][:,j,i]
    liqwat_rev=nc_file_data['liq_wat'][:,j,i]
    ps_data = nc_file_data['ps'][j,i]
        
    #The 3D fields above are apparently on grid vertical interfaces. In the file external_ic.F90/get_nggps_ic subroutine in FV3, these fields
    #are further processed to get to the vertical grid centers/means.
    
    # following remap_scalar_nggps in external_ic.F90
    levp_data = len(sphum_rev)
    
    ak_rev = vgrid["ak"][::-1]
    bk_rev = vgrid["bk"][::-1]
    ak_rev[0] = np.max([1.0E-9, ak_rev[0]])
    
    ptop_data = ak_rev[1]
            
    pressure_from_data_rev = ak_rev + bk_rev*ps_data
    log_pressure_from_data_rev = np.log(pressure_from_data_rev)
    
    gz_rev = np.zeros(2*levp_data +1)
    pn_rev = np.zeros(2*levp_data +1)
        
    gz_rev[0:levp_data+1] = zh_rev*grav
    pn_rev[0:levp_data+1] = log_pressure_from_data_rev
    k2 = np.max([10, levp_data/2])
    for k in range(levp_data+1,levp_data+k2-1):
        #do k=km+2, km+k2
        l = 2*(levp_data+1) - k
        gz_rev[k] = 2.*gz_rev[levp_data+1] - gz_rev[l]
        pn_rev[k] = 2.*pn_rev[levp_data+1] - pn_rev[l]
    
    phis = zh_rev[levp_data]*grav
    
    for k in range(levp_data+k2-2,0,-1):
        #do k=km+k2-1, 2, -1
        if (phis <= gz_rev[k] and phis >= gz_rev[k+1]):
            log_ps_calc = pn_rev[k] + (pn_rev[k+1]-pn_rev[k])*(gz_rev[k]-phis)/(gz_rev[k]-gz_rev[k+1])
            break
    ps_calc = np.exp(log_ps_calc)
        
    pressure_model_interfaces_rev = np.zeros(nlevs_model+1)
    log_pressure_model_interfaces_rev = np.zeros(nlevs_model+1)
    pressure_model_interfaces_rev[0] = ak_rev[1]
    log_pressure_model_interfaces_rev[0] = np.log(pressure_model_interfaces_rev[0])
    for k in range(1,nlevs_model+1):
        pressure_model_interfaces_rev[k] = ak_rev[k+1] + bk_rev[k+1]*ps_calc
        log_pressure_model_interfaces_rev[k] = np.log(pressure_model_interfaces_rev[k])
    
    pressure_thickness_model_rev = np.zeros(nlevs_model)
    for k in range(0,nlevs_model):
        pressure_thickness_model_rev[k] = pressure_model_interfaces_rev[k+1] - pressure_model_interfaces_rev[k]
    
    sphum_model_rev = fv3_remap.mappm(levp_data, pressure_from_data_rev[np.newaxis, :], sphum_rev[np.newaxis, :], nlevs_model, pressure_model_interfaces_rev[np.newaxis, :], 1, 1, 0, 8, ptop_data)
    sphum_model_rev_3d = fv3_remap.fillq(1, nlevs_model, 1, np.expand_dims(sphum_model_rev, axis=2), pressure_thickness_model_rev[np.newaxis, :])
    sphum_model_rev = sphum_model_rev_3d[:,:,0]
    
    o3_model_rev = fv3_remap.mappm(levp_data, pressure_from_data_rev[np.newaxis, :], o3_rev[np.newaxis, :], nlevs_model, pressure_model_interfaces_rev[np.newaxis, :], 1, 1, 0, 8, ptop_data)
    o3_model_rev_3d = fv3_remap.fillz(1, nlevs_model, 1, np.expand_dims(o3_model_rev, axis=2), pressure_thickness_model_rev[np.newaxis, :])
    o3_model_rev = o3_model_rev_3d[:,:,0]
    
    liqwat_model_rev = fv3_remap.mappm(levp_data, pressure_from_data_rev[np.newaxis, :], liqwat_rev[np.newaxis, :], nlevs_model, pressure_model_interfaces_rev[np.newaxis, :], 1, 1, 0, 8, ptop_data)
    liqwat_model_rev_3d = fv3_remap.fillz(1, nlevs_model, 1, np.expand_dims(liqwat_model_rev, axis=2), pressure_thickness_model_rev[np.newaxis, :])
    liqwat_model_rev = liqwat_model_rev_3d[:,:,0]
    
    if old_chgres:
        gz_fv = np.zeros(nlevs_model+1)
        gz_fv[-1] = phis
        m = 0
        for k in range(0,nlevs_model):
            for l in range(m, levp_data+k2-1):
                if ( (log_pressure_model_interfaces_rev[k] <= pn_rev[l+1]) and (log_pressure_model_interfaces_rev[k] >= pn_rev[l]) ):
                    gz_fv[k] = gz_rev[l] + (gz_rev[l+1]-gz_rev[l])*(log_pressure_model_interfaces_rev[k]-pn_rev[l])/(pn_rev[l+1]-pn_rev[l])
                    break
            m = l
        
        temp_model_rev = np.zeros(nlevs_model)
        for k in range(0, nlevs_model):
            temp_model_rev[k] = (gz_fv[k]-gz_fv[k+1])/(rdgas*(log_pressure_model_interfaces_rev[k+1]-log_pressure_model_interfaces_rev[k])*(1.+zvir*sphum_model_rev[0,k]) )
    else:
        temp_rev = nc_file_data['t'][:,j,i]
        
        temp_model_rev = fv3_remap.mappm(levp_data, pressure_from_data_rev[np.newaxis, :], temp_rev[np.newaxis, :], nlevs_model, pressure_model_interfaces_rev[np.newaxis, :], 1, 1, 2, 4, ptop_data)
        
    
    icewat_model_rev = np.zeros(nlevs_model)
    all_liquid_threshold = 273.16
    all_ice_threshold = 233.16
    intermediate_threshold = 258.16
    cloud_ice_mixing_ratio_threshold = 1.0E-5
    for k in range(0, nlevs_model):
        cloud_water = liqwat_model_rev[0][k]
        if (temp_model_rev[k] > all_liquid_threshold):
            liqwat_model_rev[0][k] = cloud_water
            icewat_model_rev[k] = 0.0
        elif (temp_model_rev[k] < all_ice_threshold):
            liqwat_model_rev[0][k] = 0.0
            icewat_model_rev[k] = cloud_water
        else:
            if k == 0:
                liqwat_model_rev[0][k] = cloud_water*(temp_model_rev[k]-all_ice_threshold)/(all_liquid_threshold - all_ice_threshold)
                icewat_model_rev[k] = cloud_water - liqwat_model_rev[0][k]
            else:
                if (temp_model_rev[k] < intermediate_threshold and icewat_model_rev[k-1] > cloud_ice_mixing_ratio_threshold):
                    liqwat_model_rev[0][k] = 0.0
                    icewat_model_rev[k] = cloud_water
                else:
                    liqwat_model_rev[0][k] = cloud_water*(temp_model_rev[k]-all_ice_threshold)/(all_liquid_threshold - all_ice_threshold)
                    icewat_model_rev[k] = cloud_water - liqwat_model_rev[0][k]
        (liqwat_model_rev[0][k], dummy_rain, icewat_model_rev[k], dummy_snow) = fv3_remap.mp_auto_conversion(liqwat_model_rev[0][k], icewat_model_rev[k])
    
    filename_pattern = '*grid.tile{0}.nc'.format(tile)
    
    for f_name in os.listdir(dir):
       if fnmatch.fnmatch(f_name, filename_pattern):
          filename = f_name
    if not filename:
        message = 'No filenames matching the pattern {0} found in {1}'.format(filename_pattern,dir)
        logging.critical(message)
        raise Exception(message)
    
    u_s = nc_file_data['u_s'][:,:,:].swapaxes(1,2)
    v_s = nc_file_data['v_s'][:,:,:].swapaxes(1,2)
    u_w = nc_file_data['u_w'][:,:,:].swapaxes(1,2)
    v_w = nc_file_data['v_w'][:,:,:].swapaxes(1,2)
    
    #print u_s.shape, v_s.shape
    #print u_w.shape, v_w.shape
    
    
    nc_file_grid = Dataset('{0}/{1}'.format(dir,filename))
    nc_file_sfc = Dataset('{0}/{1}'.format(dir,'sfc_data.tile{0}.nc'.format(tile)))
        
    #read in supergrid longitude and latitude
    lon_super = np.array(nc_file_grid['x']).swapaxes(0,1)   #[lat,lon] or [y,x]   #.swapaxes(0,1)
    lat_super = np.array(nc_file_grid['y']).swapaxes(0,1)    #[lat,lon] or [y,x]   #.swapaxes(0,1)
    
    num_agrid_x = int(0.5*(lon_super.shape[0]-1))
    num_agrid_y = int(0.5*(lon_super.shape[1]-1))
        
    # dgrid = np.zeros((2, num_agrid_x+1, num_agrid_y+1))
    # for m in range(0, num_agrid_x+1):
    #     for n in range(0, num_agrid_y+1):
    #         dgrid[0,m,n] = lon_super[2*m,2*n]
    #         dgrid[1,m,n] = lat_super[2*m,2*n]
    # for m in range(0, num_agrid_x):
    #     print m, dgrid[0,m,0], dgrid[0,m+1,0]
    
    #p1 = np.asarray((dgrid[0,i,j],dgrid[1,i,j]))
    #p2 = np.asarray((dgrid[0,i+1,j],dgrid[1,i+1,j]))
    
    #find orientation
    #A-grid point
    agrid_super_i_index = 2*i + 1
    agrid_super_j_index = 2*j + 1
    point_on_agrid = np.asarray((lon_super[agrid_super_i_index,agrid_super_j_index],lat_super[agrid_super_i_index,agrid_super_j_index]))
    
    test_dgrid_points = [(lon_super[agrid_super_i_index+1,agrid_super_j_index],lat_super[agrid_super_i_index+1,agrid_super_j_index]),\
                         (lon_super[agrid_super_i_index-1,agrid_super_j_index],lat_super[agrid_super_i_index-1,agrid_super_j_index]),\
                         (lon_super[agrid_super_i_index,agrid_super_j_index+1],lat_super[agrid_super_i_index,agrid_super_j_index+1]),\
                         (lon_super[agrid_super_i_index,agrid_super_j_index-1],lat_super[agrid_super_i_index,agrid_super_j_index-1])]
    
    test_lon_diff = [p[0] - point_on_agrid[0] for p in test_dgrid_points]
    test_lat_diff = [p[1] - point_on_agrid[1] for p in test_dgrid_points]
    
    east_test_point = np.argmax(test_lon_diff)
    north_test_point = np.argmax(test_lat_diff)
    
    #print 'east test point=',east_test_point
    #print 'north_test_point=',north_test_point
    
    if east_test_point == 0:
        #longitude increases most along the positive i axis
        if north_test_point == 2:
            #latitude increases most along the positive j axis
            #     ---> j+ north
            #     |
            #     V
            #     i+ east
            
            #calculation of zonal wind on first (south) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*(i+1),2*j],lat_super[2*(i+1),2*j]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_s = nc_file_data['u_s'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on second (north) D-grid point
            p1 = np.asarray((lon_super[2*i,2*(j+1)],lat_super[2*i,2*(j+1)]))
            p2 = np.asarray((lon_super[2*(i+1),2*(j+1)],lat_super[2*(i+1),2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_n = nc_file_data['u_s'][:,j+1,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j+1,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #u_agrid_rev = 0.5*(u_s + u_n)
            
            #calculation of meridionial wind on first (west) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*i,2*(j+1)],lat_super[2*i,2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_w = nc_file_data['u_w'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of meridionial wind on second (east) D-grid point
            p1 = np.asarray((lon_super[2*(i+1),2*j],lat_super[2*(i+1),2*j]))
            p2 = np.asarray((lon_super[2*(i+1),2*(j+1)],lat_super[2*(i+1),2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_e = nc_file_data['u_w'][:,j,i+1]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i+1]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #v_agrid_rev = 0.5*(v_w + v_e)
        elif north_test_point == 3:
            #latitude increases most along the negative j axis
            # <--- j- north
            #    |
            #    V
            #    i+ east
            #calculation of zonal wind on first (south) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*(i+1),2*j],lat_super[2*(i+1),2*j]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_s = nc_file_data['u_s'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on second (north) D-grid point
            p1 = np.asarray((lon_super[2*i,2*(j-1)],lat_super[2*i,2*(j-1)]))
            p2 = np.asarray((lon_super[2*(i+1),2*(j-1)],lat_super[2*(i+1),2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_n = nc_file_data['u_s'][:,j-1,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j-1,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #u_agrid_rev = 0.5*(u_s + u_n)
            
            #calculation of meridionial wind on first (west) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*i,2*(j-1)],lat_super[2*i,2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_w = nc_file_data['u_w'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of meridionial wind on second (east) D-grid point
            p1 = np.asarray((lon_super[2*(i+1),2*j],lat_super[2*(i+1),2*j]))
            p2 = np.asarray((lon_super[2*(i+1),2*(j-1)],lat_super[2*(i+1),2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_e = nc_file_data['u_w'][:,j,i+1]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i+1]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #v_agrid_rev = 0.5*(v_w + v_e)
        else:
            print 'unknown grid orientation'
    elif east_test_point == 1:
        #longitude increases most along the negative i axis
        if north_test_point == 2:
            #latitude increases most along the positive j axis
            #     i- east
            #     ^
            #     |
            #     ---> j+ north
            #calculation of zonal wind on first (south) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*(i-1),2*j],lat_super[2*(i-1),2*j]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_s = nc_file_data['u_s'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on second (north) D-grid point
            p1 = np.asarray((lon_super[2*i,2*(j+1)],lat_super[2*i,2*(j+1)]))
            p2 = np.asarray((lon_super[2*(i-1),2*(j+1)],lat_super[2*(i-1),2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_n = nc_file_data['u_s'][:,j+1,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j+1,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #u_agrid_rev = 0.5*(u_s + u_n)
            
            #calculation of meridionial wind on first (west) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*i,2*(j+1)],lat_super[2*i,2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_w = nc_file_data['u_w'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of meridionial wind on second (east) D-grid point
            p1 = np.asarray((lon_super[2*(i-1),2*j],lat_super[2*(i-1),2*j]))
            p2 = np.asarray((lon_super[2*(i-1),2*(j+1)],lat_super[2*(i-1),2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_e = nc_file_data['u_w'][:,j,i-1]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i-1]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #v_agrid_rev = 0.5*(v_w + v_e)
        elif north_test_point == 3:
            #latitude increases most along the negative j axis
            #     i- east
            #     ^
            #     |
            # <--- j- north
            #calculation of zonal wind on first (south) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*(i-1),2*j],lat_super[2*(i-1),2*j]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_s = nc_file_data['u_s'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on second (north) D-grid point
            p1 = np.asarray((lon_super[2*i,2*(j-1)],lat_super[2*i,2*(j-1)]))
            p2 = np.asarray((lon_super[2*(i-1),2*(j-1)],lat_super[2*(i-1),2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_n = nc_file_data['u_s'][:,j-1,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j-1,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #u_agrid_rev = 0.5*(u_s + u_n)
            
            #calculation of meridionial wind on first (west) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*i,2*(j-1)],lat_super[2*i,2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_w = nc_file_data['u_w'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of meridionial wind on second (east) D-grid point
            p1 = np.asarray((lon_super[2*(i-1),2*j],lat_super[2*(i-1),2*j]))
            p2 = np.asarray((lon_super[2*(i-1),2*(j-1)],lat_super[2*(i-1),2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_e = nc_file_data['u_w'][:,j,i-1]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i-1]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #v_agrid_rev = 0.5*(v_w + v_e)
        else:
            print 'unknown grid orientation'
    elif east_test_point == 2:
        #longitude increases most along the positive j axis
        if north_test_point == 0:
            #latitude increases most along the positive i axis
            #     ---> j+ east
            #     |
            #     V
            #     i+ north
            #calculation of zonal wind on first (south) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*i,2*(j+1)],lat_super[2*i,2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_s = nc_file_data['u_s'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on second (north) D-grid point
            p1 = np.asarray((lon_super[2*(i+1),2*j],lat_super[2*(i+1),2*j]))
            p2 = np.asarray((lon_super[2*(i+1),2*(j+1)],lat_super[2*(i+1),2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_n = nc_file_data['u_s'][:,j,i+1]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i+1]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #u_agrid_rev = 0.5*(u_s + u_n)
            
            #calculation of meridionial wind on first (west) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*(i+1),2*j],lat_super[2*(i+1),2*j]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_w = nc_file_data['u_w'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of meridionial wind on second (east) D-grid point
            p1 = np.asarray((lon_super[2*i,2*(j+1)],lat_super[2*i,2*(j+1)]))
            p2 = np.asarray((lon_super[2*(i+1),2*(j+1)],lat_super[2*(i+1),2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_e = nc_file_data['u_w'][:,j+1,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j+1,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #v_agrid_rev = 0.5*(v_w + v_e)
        elif north_test_point == 1:
            #latitude increases most along the negative i axis
            #     i- north
            #     ^
            #     |
            #     ---> j+ east
            #calculation of zonal wind on first (south) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*i,2*(j+1)],lat_super[2*i,2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_s = nc_file_data['u_s'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on second (north) D-grid point
            p1 = np.asarray((lon_super[2*(i-1),2*j],lat_super[2*(i-1),2*j]))
            p2 = np.asarray((lon_super[2*(i-1),2*(j+1)],lat_super[2*(i-1),2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_n = nc_file_data['u_s'][:,j,i-1]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i-1]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #u_agrid_rev = 0.5*(u_s + u_n)
            
            #calculation of meridionial wind on first (west) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*(i-1),2*j],lat_super[2*(i-1),2*j]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_w = nc_file_data['u_w'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of meridionial wind on second (east) D-grid point
            p1 = np.asarray((lon_super[2*i,2*(j+1)],lat_super[2*i,2*(j+1)]))
            p2 = np.asarray((lon_super[2*(i-1),2*(j+1)],lat_super[2*(i-1),2*(j+1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_e = nc_file_data['u_w'][:,j+1,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j+1,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #v_agrid_rev = 0.5*(v_w + v_e)
        else:
            print 'unknown grid orientation'
    elif east_test_point == 3:
        #longitude increases most along the negative j axis
        if north_test_point == 0:
            #latitude increases most along the positive i axis
            # <--- j- east
            #    |
            #    V
            #    i+ north
            #calculation of zonal wind on first (south) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*i,2*(j-1)],lat_super[2*i,2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_s = nc_file_data['u_s'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on second (north) D-grid point
            p1 = np.asarray((lon_super[2*(i+1),2*j],lat_super[2*(i+1),2*j]))
            p2 = np.asarray((lon_super[2*(i+1),2*(j-1)],lat_super[2*(i+1),2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_n = nc_file_data['u_s'][:,j,i+1]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i+1]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #u_agrid_rev = 0.5*(u_s + u_n)
            
            #calculation of meridionial wind on first (west) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*(i+1),2*j],lat_super[2*(i+1),2*j]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_w = nc_file_data['u_w'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of meridionial wind on second (east) D-grid point
            p1 = np.asarray((lon_super[2*i,2*(j-1)],lat_super[2*i,2*(j-1)]))
            p2 = np.asarray((lon_super[2*(i+1),2*(j-1)],lat_super[2*(i+1),2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_e = nc_file_data['u_w'][:,j-1,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j-1,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #v_agrid_rev = 0.5*(v_w + v_e)
        elif north_test_point == 1:
            #latitude increases most along the negative i axis
            #     i- north
            #     ^
            #     |
            # <--- j- east
            #calculation of zonal wind on first (south) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*i,2*(j-1)],lat_super[2*i,2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_s = nc_file_data['u_s'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on second (north) D-grid point
            p1 = np.asarray((lon_super[2*(i-1),2*j],lat_super[2*(i-1),2*j]))
            p2 = np.asarray((lon_super[2*(i-1),2*(j-1)],lat_super[2*(i-1),2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            u_n = nc_file_data['u_s'][:,j,i-1]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_s'][:,j,i-1]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #u_agrid_rev = 0.5*(u_s + u_n)
            
            #calculation of meridionial wind on first (west) D-grid point
            p1 = np.asarray((lon_super[2*i,2*j],lat_super[2*i,2*j]))
            p2 = np.asarray((lon_super[2*(i-1),2*j],lat_super[2*(i-1),2*j]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_w = nc_file_data['u_w'][:,j,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of meridionial wind on second (east) D-grid point
            p1 = np.asarray((lon_super[2*i,2*(j-1)],lat_super[2*i,2*(j-1)]))
            p2 = np.asarray((lon_super[2*(i-1),2*(j-1)],lat_super[2*(i-1),2*(j-1)]))
            p3 = fv3_remap.mid_pt_sphere(p1*deg_to_rad, p2*deg_to_rad)
            e1 = fv3_remap.get_unit_vect2(p1*deg_to_rad, p2*deg_to_rad)
            (ex, ey) = fv3_remap.get_latlon_vector(p3)
            v_e = nc_file_data['u_w'][:,j-1,i]*fv3_remap.inner_prod(e1, ex) + nc_file_data['v_w'][:,j-1,i]*fv3_remap.inner_prod(e1, ey)
            
            #calculation of zonal wind on A-grid (simple average for now)
            #v_agrid_rev = 0.5*(v_w + v_e)
        else:
            print 'unknown grid orientation'
    
    #print 'u (A-grid)', u_agrid_rev
    #print 'v (A-grid)', v_agrid_rev
    
    u_s_model_rev = fv3_remap.mappm(levp_data, pressure_from_data_rev[np.newaxis, :], u_s[np.newaxis, :], nlevs_model, pressure_model_interfaces_rev[np.newaxis, :], 1, 1, -1, 8, ptop_data)
    u_n_model_rev = fv3_remap.mappm(levp_data, pressure_from_data_rev[np.newaxis, :], u_n[np.newaxis, :], nlevs_model, pressure_model_interfaces_rev[np.newaxis, :], 1, 1, -1, 8, ptop_data)
    v_w_model_rev = fv3_remap.mappm(levp_data, pressure_from_data_rev[np.newaxis, :], v_w[np.newaxis, :], nlevs_model, pressure_model_interfaces_rev[np.newaxis, :], 1, 1, -1, 8, ptop_data)
    v_e_model_rev = fv3_remap.mappm(levp_data, pressure_from_data_rev[np.newaxis, :], v_e[np.newaxis, :], nlevs_model, pressure_model_interfaces_rev[np.newaxis, :], 1, 1, -1, 8, ptop_data)
    
    u_model_rev = np.zeros(nlevs_model)
    v_model_rev = np.zeros(nlevs_model)
    #print u_s_model_rev
    u_model_rev = 0.5*(u_s_model_rev + u_n_model_rev)
    v_model_rev = 0.5*(v_w_model_rev + v_e_model_rev)
    
    #print 'u (A-grid) on model levels', u_model_rev
    #print 'v (A-grid) on model levels', v_model_rev
    
    #STILL NEED TO PUT u,v (A-grid) ON MODEL LAYER CENTERS!!!
        
    nc_file_grid.close()
    nc_file_data.close()
    nc_file_sfc.close()
    
    # dyn_filename_pattern = 'dynf*.tile{0}.nc'.format(tile)
    # phy_filename_pattern = 'phyf*.tile{0}.nc'.format(tile)
    # 
    # dyn_filenames = []
    # phy_filenames = []
    # for f_name in os.listdir(forcing_dir):
    #    if fnmatch.fnmatch(f_name, dyn_filename_pattern):
    #       dyn_filenames.append(f_name)
    #    if fnmatch.fnmatch(f_name, phy_filename_pattern):
    #       phy_filenames.append(f_name)
    # if not dyn_filenames:
    #     message = 'No filenames matching the pattern {0} found in {1}'.format(dyn_filename_pattern,dir)
    #     logging.critical(message)
    #     raise Exception(message)
    # if not phy_filenames:
    #     message = 'No filenames matching the pattern {0} found in {1}'.format(phy_filename_pattern,dir)
    #     logging.critical(message)
    #     raise Exception(message)
    # dyn_filenames = sorted(dyn_filenames)
    # phy_filenames = sorted(phy_filenames)
    # 
    # if (len(dyn_filenames) != len(phy_filenames)):
    #     message = 'The number of dyn files and phy files in {0} matching the patterns does not match.'.format(dir)
    #     logging.critical(message)
    #     raise Exception(message)
    # 
    # n_files = len(dyn_filenames)
    # 
    # u_layers = []
    # v_layers = []
    # time_dyn_hours = []
    # for filename in dyn_filenames:
    #     nc_file = Dataset('{0}/{1}'.format(forcing_dir,filename))
    # 
    #     nlevs=len(nc_file.dimensions['pfull'])
    # 
    #     u_layers.append(nc_file['ugrd'][0,:,j,i])
    #     v_layers.append(nc_file['vgrd'][0,:,j,i])
    # 
    #     time_dyn_hours.append(nc_file['time'][0])
    # 
    #     nc_file.close()
    # u_layers = np.asarray(u_layers)
    # v_layers = np.asarray(v_layers)
    # print 'u from dyn file', u_layers[0]
    # print 'v from dyn file',v_layers[0]
    
    # if old_chgres: 
    #      #temperature
    #      gz=state_data["z"]*grav
    #      pn1=np.zeros([nlevs+1])
    #      temp=np.zeros([nlevs])
    #      for k in range(nlevs+1):
    #        pn1[k]=np.log(vgrid_data["ak"][k]+state_data["p_surf"]*vgrid_data["bk"][k])
    #      for k in range(nlevs):
    #        temp[k] = (gz[k]-gz[k+1])/( rdgas*(pn1[k+1]-pn1[k])*(1.+zvir*state_data["qv"][k]) )
    #      print temp
    #      #state_data["T"] = temp
    #      #state_data["pres"] = np.exp(pn1[0:nlevs])
    #
    # else:
    #     #gfs_data.tileX.nc files created from chgres_cube already containt temperature and pressure profiles(well, surface pressure and delp); use those
    #     #older version of global_chgres did not include these vars
    #     t = nc_file['t'][::-1,j,i]
    # 
    #     delp = nc_file['delp'][::-1,j,i]
    # 
    #     p = np.zeros(nlevs)
    #     p[0] = ps
    #     for k in range(1, nlevs):
    #         p[k] = p[k-1] - delp[k-1]
            
    

    
    
        
    #put data in a dictionary
    # if old_chgres:
    #     state = {
    #         "nlevs": nlevs,
    #         "z": zh,
    #         "u": ucomp,
    #         "v": vcomp,
    #         "qv": sphum,
    #         "o3": o3,
    #         "ql": liqwat,
    #         "p_surf": ps
    #     }
    # else:
    
    # print zh_rev[::-1]
    # print u_model_rev[0][::-1]
    # print v_model_rev[0][::-1]
    # print sphum_model_rev[0][::-1]
    # print o3_model_rev[0][::-1]
    # print liqwat_model_rev[0][::-1]
    # print ps_calc
    # print temp_model_rev[::-1]
    # print pressure_model_interfaces_rev[::-1]
    
    
    pressure_model_interfaces = pressure_model_interfaces_rev[::-1]
    pressure_model = np.zeros(nlevs_model)
    for k in range(0,nlevs_model):
        #from gmtb_scm_vgrid
        pressure_model[k] = ((1.0/(rocp+1.0))*(pressure_model_interfaces[k]**(rocp+1.0) - pressure_model_interfaces[k+1]**(rocp+1.0))/(pressure_model_interfaces[k] - pressure_model_interfaces[k+1]))**(1.0/rocp)
    
    #print pressure_model
    
    
    #exit()
    
    state = {
        "nlevs": nlevs_model,
        "z": zh_rev[::-1],
        "u": u_model_rev[0][::-1],
        "v": v_model_rev[0][::-1],
        "qv": sphum_model_rev[0][::-1],
        "o3": o3_model_rev[0][::-1],
        "ql": liqwat_model_rev[0][::-1],
        "p_surf": ps_calc,
        "T": temp_model_rev[::-1],
        "pres": pressure_model,
        "pres_i": pressure_model_interfaces
    }
        
    return state

def get_UFS_surface_data(dir, tile, i, j, old_chgres):
    """Get the surface data for the given tile and indices"""
    
    nc_file = Dataset('{0}/{1}'.format(dir,'sfc_data.tile{0}.nc'.format(tile)))
    
    if old_chgres:
        ts_in=nc_file['tsea'][j,i]

        # land state
        stc_in=nc_file['stc'][:,j,i]
        smc_in=nc_file['smc'][:,j,i]
        slc_in=nc_file['slc'][:,j,i]
        tg3_in=nc_file['tg3'][j,i]

        # surface properties
        uustar_in=nc_file['uustar'][j,i]
        alvsf_in=nc_file['alvsf'][j,i]
        alvwf_in=nc_file['alvwf'][j,i]
        alnsf_in=nc_file['alnsf'][j,i]
        alnwf_in=nc_file['alnwf'][j,i]
        facsf_in=nc_file['facsf'][j,i]
        facwf_in=nc_file['facwf'][j,i]
        styp_in=nc_file['stype'][j,i]
        slope_in=nc_file['slope'][j,i]
        vtyp_in=nc_file['vtype'][j,i]
        vfrac_in=nc_file['vfrac'][j,i]
        shdmin_in=nc_file['shdmin'][j,i]
        shdmax_in=nc_file['shdmax'][j,i]
        zorl_in=nc_file['zorl'][j,i]
        slmsk_in=nc_file['slmsk'][j,i]
        canopy_in=nc_file['canopy'][j,i]
        hice_in=nc_file['hice'][j,i]
        fice_in=nc_file['fice'][j,i]
        tisfc_in=nc_file['tisfc'][j,i]
        snwdph_in=nc_file['snwdph'][j,i]
        snoalb_in=nc_file['snoalb'][j,i]
        sheleg_in=nc_file['sheleg'][j,i]
    else:
        #the sfc_data.tileX.nc files created from chgres_cube have an extra time dimension in front compared to those created from global_chgres
        ts_in=nc_file['tsea'][0,j,i]
        
        # land state
        stc_in=nc_file['stc'][0,:,j,i]
        smc_in=nc_file['smc'][0,:,j,i]
        slc_in=nc_file['slc'][0,:,j,i]
        tg3_in=nc_file['tg3'][0,j,i]
        
        # surface properties
        uustar_in=nc_file['uustar'][0,j,i]
        alvsf_in=nc_file['alvsf'][0,j,i]
        alvwf_in=nc_file['alvwf'][0,j,i]
        alnsf_in=nc_file['alnsf'][0,j,i]
        alnwf_in=nc_file['alnwf'][0,j,i]
        facsf_in=nc_file['facsf'][0,j,i]
        facwf_in=nc_file['facwf'][0,j,i]
        styp_in=nc_file['stype'][0,j,i]
        slope_in=nc_file['slope'][0,j,i]
        vtyp_in=nc_file['vtype'][0,j,i]
        vfrac_in=nc_file['vfrac'][0,j,i]
        shdmin_in=nc_file['shdmin'][0,j,i]
        shdmax_in=nc_file['shdmax'][0,j,i]
        zorl_in=nc_file['zorl'][0,j,i]
        slmsk_in=nc_file['slmsk'][0,j,i]
        canopy_in=nc_file['canopy'][0,j,i]
        hice_in=nc_file['hice'][0,j,i]
        fice_in=nc_file['fice'][0,j,i]
        tisfc_in=nc_file['tisfc'][0,j,i]
        snwdph_in=nc_file['snwdph'][0,j,i]
        snoalb_in=nc_file['snoalb'][0,j,i]
        sheleg_in=nc_file['sheleg'][0,j,i]
    
    nc_file.close()
    
    #put data in a dictionary
    surface = {
        "T_surf": ts_in,
        "stc": stc_in,
        "smc": smc_in,
        "slc": slc_in,
        "tg3": tg3_in,
        "uustar": uustar_in,
        "alvsf": alvsf_in,
        "alvwf": alvwf_in,
        "alnsf": alnsf_in,
        "alnwf": alnwf_in,
        "facsf": facsf_in,
        "facwf": facwf_in,
        "styp": styp_in,
        "slope": slope_in,
        "vtyp": vtyp_in,
        "vfrac": vfrac_in,
        "shdmin": shdmin_in,
        "shdmax": shdmax_in,
        "zorl": zorl_in,
        "slmsk": slmsk_in,
        "canopy": canopy_in,
        "hice": hice_in,
        "fice": fice_in,
        "tisfc": tisfc_in,
        "snwdph": snwdph_in,
        "snoalb": snoalb_in,
        "sheleg": sheleg_in
    }
    return surface

def get_UFS_oro_data(dir, tile, i, j):
    """Get the orographic data for the given tile and indices"""
    
    filename_pattern = 'oro_data.tile{0}.nc'.format(tile)
    for f_name in os.listdir(dir):
       if fnmatch.fnmatch(f_name, filename_pattern):
          filename = f_name
    
    nc_file = Dataset('{0}/{1}'.format(dir,filename))
    
    # orographyic properties
    stddev_in=nc_file['stddev'][j,i]
    convexity_in=nc_file['convexity'][j,i]
    oa1_in=nc_file['oa1'][j,i]
    oa2_in=nc_file['oa2'][j,i]
    oa3_in=nc_file['oa3'][j,i]
    oa4_in=nc_file['oa4'][j,i]
    ol1_in=nc_file['ol1'][j,i]
    ol2_in=nc_file['ol2'][j,i]
    ol3_in=nc_file['ol3'][j,i]
    ol4_in=nc_file['ol4'][j,i]
    theta_in=nc_file['theta'][j,i]
    gamma_in=nc_file['gamma'][j,i]
    sigma_in=nc_file['sigma'][j,i]
    elvmax_in=nc_file['elvmax'][j,i]
    
    nc_file.close()
    
    #put data in a dictionary
    oro = {
        "stddev": stddev_in,
        "convexity": convexity_in,
        "oa1": oa1_in,
        "oa2": oa2_in,
        "oa3": oa3_in,
        "oa4": oa4_in,
        "ol1": ol1_in,
        "ol2": ol2_in,
        "ol3": ol3_in,
        "ol4": ol4_in,
        "theta": theta_in,
        "gamma": gamma_in,
        "sigma": sigma_in,
        "elvmax": elvmax_in
    }
    return oro

def get_UFS_vgrid_data(dir):
    """Get the vertical grid data for resolution of the data within the IC directory"""
    
    nc_file = Dataset('{0}/{1}'.format(dir,'gfs_ctrl.nc'))
    
    # vertical coordinate definition
    # GJF: it looks like there is an extra level on top that represents 0 Pa, otherwise these values are for vertical grid interfaces
    ak=nc_file['vcoord'][0,::-1]
    bk=nc_file['vcoord'][1,::-1]
    
    #GJF: in external_ic.F90, when external_eta is true (which it apparently is for FV3GFS runs), the top value is ignored
    #ak = ak[0:len(ak)-1]
    #bk = bk[0:len(bk)-1]
    
    nc_file.close()
    
    vgrid = {
        "ak": ak,
        "bk": bk,
        "nlevs": len(ak)-2  #full grid levels are interfaces - 1 and there is an extra level on top (subtract 2)
    }
    
    return vgrid    

def get_UFS_grid_area(dir, tile, i, j):
    """Get the horizontal grid cell area for the given tile and indices"""
    #this information is in the supergrid files
    
    filename_pattern = '*grid.tile{0}.nc'.format(tile)
    
    for f_name in os.listdir(dir):
       if fnmatch.fnmatch(f_name, filename_pattern):
          filename = f_name
    if not filename:
        message = 'No filenames matching the pattern {0} found in {1}'.format(filename_pattern,dir)
        logging.critical(message)
        raise Exception(message)
    
    nc_file = Dataset('{0}/{1}'.format(dir,filename))
    
    # extract out area of grid cell
    
    #calculate supergrid indices from regular grid indices
    jpt2 = j*2+1
    ipt2 = i*2+1
    
    #from Phil Pegion: the area is calculated by adding up the 4 components of the contained supergrid cells
    area_in=nc_file['area'][jpt2-1:jpt2+1,ipt2-1:ipt2+1]
    
    return area_in.sum()

def get_UFS_forcing_data(nlevs, state, dir, tile, i, j):
    """Get the horizontal and vertical advective tendencies for the given tile and indices"""
    
    #Note: this is a placeholder function that sets forcing to 0, but will need to be filled out in the future from custom FV3 output
    
    dyn_filename_pattern = 'dynf*.tile{0}.nc'.format(tile)
    phy_filename_pattern = 'phyf*.tile{0}.nc'.format(tile)
    
    dyn_filenames = []
    phy_filenames = []
    for f_name in os.listdir(dir):
       if fnmatch.fnmatch(f_name, dyn_filename_pattern):
          dyn_filenames.append(f_name)
       if fnmatch.fnmatch(f_name, phy_filename_pattern):
          phy_filenames.append(f_name)
    if not dyn_filenames:
        message = 'No filenames matching the pattern {0} found in {1}'.format(dyn_filename_pattern,dir)
        logging.critical(message)
        raise Exception(message)
    if not phy_filenames:
        message = 'No filenames matching the pattern {0} found in {1}'.format(phy_filename_pattern,dir)
        logging.critical(message)
        raise Exception(message)
    dyn_filenames = sorted(dyn_filenames)
    phy_filenames = sorted(phy_filenames)
    
    if (len(dyn_filenames) != len(phy_filenames)):
        message = 'The number of dyn files and phy files in {0} matching the patterns does not match.'.format(dir)
        logging.critical(message)
        raise Exception(message)
    
    n_files = len(dyn_filenames)
    
    kord_tm = -9
    kord_tr = 9
    t_min = 184.0
    q_min = 0.0
    
    p_interfaces = []
    p_layers = []
    t_layers = []
    qv_layers = []
    time_dyn_hours = []
    for filename in dyn_filenames:
        nc_file = Dataset('{0}/{1}'.format(dir,filename))
        
        nlevs=len(nc_file.dimensions['pfull'])
        
        ak = getattr(nc_file, "ak")[::-1]
        bk = getattr(nc_file, "bk")[::-1]
    
        ps=nc_file['pressfc'][0,j,i]
        
        p_interface = np.zeros(nlevs+1)
        for k in range(nlevs+1):
            p_interface[k]=ak[k]+ps*bk[k]
        
        p_interfaces.append(p_interface)
        
        p_layer = np.zeros(nlevs)
        for k in range(nlevs):
            p_layer[k] = ((1.0/(rocp+1.0))*(p_interface[k]**(rocp+1.0) - p_interface[k+1]**(rocp+1.0))/(p_interface[k] - p_interface[k+1]))**(1.0/rocp)
        
        p_layers.append(p_layer)
        
        t_layers.append(nc_file['tmp'][0,::-1,j,i])
        qv_layers.append(nc_file['spfh'][0,::-1,j,i])
            
        time_dyn_hours.append(nc_file['time'][0])
        
        nc_file.close()
    p_interfaces = np.asarray(p_interfaces)
    p_layers = np.asarray(p_layers)
    t_layers = np.asarray(t_layers)
    qv_layers = np.asarray(qv_layers)
    time_dyn_hours = np.asarray(time_dyn_hours)

    tv_layers = t_layers*(1.0 + zvir*qv_layers)
    
    dt3dt_nophys = []
    dq3dt_nophys = []
    time_phys_hours = []
    for filename in phy_filenames:
        nc_file = Dataset('{0}/{1}'.format(dir,filename))
        
        nlevs=len(nc_file.dimensions['pfull'])
        
        try:
            dt3dt_nophys.append(nc_file['dt3dt_nophys'][0,::-1,j,i])
            #dt3dt_nophys.append(nc_file['dt3dt_nophys'][0,:,j,i])
        except:
            print 'dt3dt_nophys not found in ', filename
        
        try:
            dq3dt_nophys.append(nc_file['dq3dt_nophys'][0,::-1,j,i])
            #dq3dt_nophys.append(nc_file['dq3dt_nophys'][0,:,j,i])
        except:
            print 'dq3dt_nophys not found in ', filename
        
        time_phys_hours.append(nc_file['time'][0])
                
        nc_file.close()
    dt3dt_nophys = np.asarray(dt3dt_nophys)
    dq3dt_nophys = np.asarray(dq3dt_nophys)
    time_phys_hours = np.asarray(time_phys_hours)
    
    dummy = np.zeros(1)
    
    # print(state["pres_i"])
    # print(p_interfaces[0])
    # print(p_interfaces[1])
    # 
    # print(state["pres"])
    # print(p_layers[0])
    # print(p_layers[1])
    # 
    # print(state["T"])
    # print(t_layers[0])
    # print(t_layers[1])
    # 
    # print(dt3dt_nophys[0])
    # print(dt3dt_nophys[1])
    # 
    # print(state["qv"])
    # print(qv_layers[0])
    # print(qv_layers[1])
    
    dtdt_adv = np.zeros([n_files,p_layers.shape[1]])
    dqvdt_adv = np.zeros([n_files,p_layers.shape[1]])
    valid_pres_adv = np.zeros([n_files,p_layers.shape[1]])
    valid_pres_i_adv = np.zeros([n_files,p_interfaces.shape[1]])
    
    #handle forcing from initialization to the first history file
    tv_layers_remap_1 = np.zeros([1,t_layers.shape[1]])
    qv_layers_remap_1 = np.zeros([1,qv_layers.shape[1]])
    
    #calculate new Tv at first history file time due to remapping
    tv_rev = np.zeros([1,tv_layers.shape[1]])
    log_pres_init_rev = np.zeros([1,len(state["pres_i"])])
    log_pres_1_rev = np.zeros([1,p_interfaces.shape[1]])
    
    tv_init = state["T"]*(1.0 + zvir*state["qv"])
    tv_init_rev = tv_init[::-1]
    log_pres_init_rev[0,:] = np.log(state["pres_i"][::-1])
    log_pres_1_rev[0,:] = np.log(p_interfaces[0,::-1])
    
    qv_rev = np.zeros([1,qv_layers.shape[1]])
    pres_init_rev = np.zeros([1,len(state["pres_i"])])
    pres_1_rev = np.zeros([1,p_interfaces.shape[1]])
    
    qv_init_rev = state["qv"][::-1]
    pres_init_rev[0,:] = state["pres_i"][::-1]
    pres_1_rev[0,:] = p_interfaces[0,::-1]
    
    tv_rev_new = fv3_remap.map_scalar(len(tv_init_rev), log_pres_init_rev, tv_init_rev[np.newaxis, :], dummy, len(tv_init_rev), log_pres_1_rev, 0, 0, 1, np.abs(kord_tm), t_min)
    tv_layers_remap_1[0,:] = tv_rev_new[0,::-1]
    
    dp2 = np.zeros([1,qv_rev.shape[1]])
    for k in range(0,qv_rev.shape[1]):
        dp2[0,k] = pres_1_rev[0,k+1] - pres_1_rev[0,k]
    
    qv_rev_new = fv3_remap.map1_q2(len(qv_init_rev), pres_init_rev, qv_init_rev[np.newaxis, :], len(qv_init_rev), pres_1_rev, dp2, 0, 0, 0, kord_tr, q_min)
    qv_layers_remap_1[0,:] = qv_rev_new[0,::-1]
    
    t_layers_remap_1 = tv_layers_remap_1/(1.0 + zvir*qv_layers_remap_1)
    
    # print state["T"]
    # print t_layers_remap_1[0]
    # print t_layers[0,:]
    # 
    # print state["qv"]
    # print qv_layers_remap_1[0]
    # print qv_layers[0,:]
    
    dtdt_remap_1 = np.zeros([1,t_layers.shape[1]])
    #dtdt_adv_1 = np.zeros([1,t_layers.shape[1]])
    dqvdt_remap_1 = np.zeros([1,qv_layers.shape[1]])
    #dqvdt_adv_1 = np.zeros([1,qv_layers.shape[1]])
    
    valid_pres_adv[0,:] = state["pres"]
    valid_pres_i_adv[0,:] = state["pres_i"]
    
    dqvdt_remap_1[0,:] = (qv_layers_remap_1[0,:] - state["qv"][:])/(3600.0*(time_dyn_hours[0]))
    print(dqvdt_remap_1[0,:])
    dqvdt_adv[0,:] = dq3dt_nophys[0,:] - dqvdt_remap_1[0,:]  #valid at state["pres"] levels
    print(dqvdt_adv[0,:])
    
    dtdt_remap_1[0,:] = (t_layers_remap_1[0,:] - state["T"][:])/(3600.0*(time_dyn_hours[0]))
    print(dtdt_remap_1[0,:])
    dtdt_adv[0,:] = dt3dt_nophys[0,:] - dtdt_remap_1[0,:]  #valid at state["pres"] levels
    print(dtdt_adv[0,:])
    
    tv_layers_remap = np.zeros([t_layers.shape[0],t_layers.shape[1]])
    qv_layers_remap = np.zeros([qv_layers.shape[0],qv_layers.shape[1]])
    for t in range(t_layers.shape[0]-1):
        #calculate new Tv at next time
        
        #the remapping procedure for Tv requires initial Tv, log(pres_interface)_old and log(pres_interface)_new; all are reversed to be top-first
        tv_rev = np.zeros([1,tv_layers.shape[1]])
        log_pres_1_rev = np.zeros([1,p_interfaces.shape[1]])
        log_pres_2_rev = np.zeros([1,p_interfaces.shape[1]])
        tv_rev[0,:] = tv_layers[t,::-1]
        log_pres_1_rev[0,:] = np.log(p_interfaces[t,::-1])
        log_pres_2_rev[0,:] = np.log(p_interfaces[t+1,::-1])
        
        qv_rev = np.zeros([1,qv_layers.shape[1]])
        pres_1_rev = np.zeros([1,p_interfaces.shape[1]])
        pres_2_rev = np.zeros([1,p_interfaces.shape[1]])
        qv_rev[0,:] = qv_layers[t,::-1]
        pres_1_rev[0,:] = p_interfaces[t,::-1]
        pres_2_rev[0,:] = p_interfaces[t+1,::-1]
        
        #print pres_2_rev[0,:], pres_1_rev[0,:]
        
        tv_rev_new = fv3_remap.map_scalar(tv_rev.shape[1], log_pres_1_rev, tv_rev, dummy, tv_rev.shape[1], log_pres_2_rev, 0, 0, 1, np.abs(kord_tm), t_min)
        
        dp2 = np.zeros([1,qv_rev.shape[1]])
        for k in range(0,qv_rev.shape[1]):
            dp2[0,k] = pres_2_rev[0,k+1] - pres_2_rev[0,k]
        
        qv_rev_new = fv3_remap.map1_q2(qv_rev.shape[1], pres_1_rev, qv_rev, qv_rev.shape[1], pres_2_rev, dp2, 0, 0, 0, kord_tr, q_min)
        
        tv_layers_remap[t+1,:] = tv_rev_new[0,::-1]
        qv_layers_remap[t+1,:] = qv_rev_new[0,::-1]
    
    t_layers_remap = tv_layers_remap/(1.0 + zvir*qv_layers_remap)
    
    dtdt_remap = np.zeros([t_layers.shape[0]-1,t_layers.shape[1]])
    dqvdt_remap = np.zeros([qv_layers.shape[0]-1,qv_layers.shape[1]])
    for t in range(t_layers.shape[0]-1):
        valid_pres_adv[t+1,:] = p_layers[t]
        valid_pres_i_adv[t+1,:] = p_interfaces[t]
        dqvdt_remap[t,:] = (qv_layers_remap[t+1,:] - qv_layers[t,:])/(3600.0*(time_dyn_hours[t+1] - time_dyn_hours[t]))
        print(dqvdt_remap[t,:])
        dqvdt_adv[t+1,:] = dq3dt_nophys[t+1,:] - dqvdt_remap[t,:]  #valid at p_layers[t]
        print(dqvdt_adv[t+1,:])
        dtdt_remap[t,:] = (t_layers_remap[t+1,:] - t_layers[t,:])/(3600.0*(time_dyn_hours[t+1] - time_dyn_hours[t]))
        print(dtdt_remap[t,:])
        dtdt_adv[t+1,:] = dt3dt_nophys[t+1,:] - dtdt_remap[t,:]  #valid at p_layers[t]
        print(dtdt_adv[t+1,:])
    
    for t in range(n_files):
        print "time = ", t
        #pres_1_rev = p_interfaces[t,::-1]
        #pres_2_rev = p_interfaces[t+1,::-1]
        for k in range(t_layers.shape[1]):
            print "k = ",k,"dqvdt_adv=",dqvdt_adv[t,k],dqvdt_adv[t,k]/dq3dt_nophys[t,k],"dtdt_adv=",dtdt_adv[t,k],dtdt_adv[t,k]/dt3dt_nophys[t,k],valid_pres_adv[t,k]
            #print pres_2_rev[k], pres_2_rev[k] - pres_1_rev[k]
    
    #for the original SCM forcing input file, all forcing terms should be valid on the initial pressure levels;
    #one should be able to use fv3_remap.map_scalar to remap these forcing terms to the initial pressure profile, rather
    #than resort to linear interpolation or something else.
    #(this interpolation can be removed when using DEPHY, that allows for varying pressure levels for forcing)
    
    dqvdt_adv_at_init_pres_rev = np.zeros([n_files,1,p_layers.shape[1]])
    dtdt_adv_at_init_pres_rev = np.zeros([n_files,1,p_layers.shape[1]])
    from_log_pres_rev = np.zeros([1,len(state["pres_i"])])
    to_log_pres_rev = np.zeros([1,len(state["pres_i"])])
    
    dqvdt_adv_at_init_pres_rev[0,0,:] = dqvdt_adv[0,::-1]
    dtdt_adv_at_init_pres_rev[0,0,:] = dtdt_adv[0,::-1]
    for t in range(1,n_files): #don't need to remap the first time interval because it is already valid at the initial pressure levels
        from_log_pres_rev[0,:] = np.log(valid_pres_i_adv[t,::-1])
        to_log_pres_rev[0,:] = np.log(valid_pres_i_adv[0,::-1])
        dqvdt_adv_at_init_pres_rev[t,:,:] = fv3_remap.map_scalar(p_layers.shape[1], from_log_pres_rev, dqvdt_adv[t,np.newaxis,::-1], dummy, p_layers.shape[1], to_log_pres_rev, 0, 0, 1, 1, 0.0)
        dtdt_adv_at_init_pres_rev[t,:,:] = fv3_remap.map_scalar(p_layers.shape[1], from_log_pres_rev, dtdt_adv[t,np.newaxis,::-1], dummy, p_layers.shape[1], to_log_pres_rev, 0, 0, 1, 1, 0.0)
    
    dtdt_adv_at_init_pres = dtdt_adv_at_init_pres_rev[:,0,::-1]
    dqvdt_adv_at_init_pres = dqvdt_adv_at_init_pres_rev[:,0,::-1]
    
    #if we had dynf,phyf files at every timestep (and the SCM timestep is made to match the UFS), then dqvdt_adv should be
    #applied uninterpolated for each time step. If dynf and phyf files represent time averages over the previous diagnostic period,
    #and if forcing terms are interpolatd in time in the SCM, then dqvdt_adv should represent the forcing values in the 
    #middle of time[t] and time[t+1] from dynf/phyf. That way, the time-averaged applied forcing from time[t] to time[t+1] in the SCM will 
    #be equal to what is derived from dynf/phyf. (preference should be to have option to remove time-interpolation of forcing such
    #that the constant forcing applied converged to time-step values as the diag interval approaches the time step)    
    
    #time_method = 'constant_simple'
    time_method = 'constant_interp'
    #time_method = 'gradient'
    
    if (time_method == 'constant_simple'):
        print 'Forcing should not be interpolated in time. Rather, forcing should held constant at their current values until the next forcing interval is reached.'
        ntimes = n_files
        time = np.zeros(ntimes)
        h_advec_thil = np.zeros((nlevs,ntimes),dtype=float)
        h_advec_qt = np.zeros((nlevs,ntimes),dtype=float)
        
        h_advec_qt[:,0] = dqvdt_adv_at_init_pres[0,:]
        for k in range(nlevs):
            h_advec_thil[k,0] = (p0/state["pres"][k])**kappa*dtdt_adv_at_init_pres[0,k]
        
        for t in range(1,n_files):
            time[t] = 3600.0*time_dyn_hours[t-1]
            h_advec_qt[:,t] = dqvdt_adv_at_init_pres[t,:]
            for k in range(nlevs):
                h_advec_thil[k,t] = (p0/state["pres"][k])**kappa*dtdt_adv_at_init_pres[t,k]
        for t in range(n_files):
             print h_advec_qt[:,t]
             print dqvdt_adv_at_init_pres[t,:]
             print h_advec_thil[:,t]
    elif (time_method == 'constant_interp'):
        print 'Forcing can be interpolated in time, but the time values are chosen such that forcing will effectively be held consant during a diagnostic time interval.'
        ntimes = 2*n_files
        
        time_setback = 1.0 #s
        
        time = np.zeros(ntimes)
        h_advec_thil = np.zeros((nlevs,ntimes),dtype=float)
        h_advec_qt = np.zeros((nlevs,ntimes),dtype=float)
        
        time[0] = 0.0
        time[1] = 3600.0*time_dyn_hours[0] - time_setback #forcing period should extend from beginning of diagnostic period to right BEFORE the next one
        h_advec_qt[:,0] = dqvdt_adv_at_init_pres[0,:]
        h_advec_qt[:,1] = h_advec_qt[:,0]
        for k in range(nlevs):
            h_advec_thil[k,0] = (p0/state["pres"][k])**kappa*dtdt_adv_at_init_pres[0,k]
        h_advec_thil[:,1] = h_advec_thil[:,0]
        
        for t in range(1,n_files):
            time[2*t] = 3600.0*time_dyn_hours[t-1]
            time[2*t+1] = 3600*time_dyn_hours[t] - time_setback
            
            h_advec_qt[:,2*t] = dqvdt_adv_at_init_pres[t,:]
            h_advec_qt[:,2*t+1] = h_advec_qt[:,2*t]
            for k in range(nlevs):
                h_advec_thil[k,2*t] = (p0/state["pres"][k])**kappa*dtdt_adv_at_init_pres[t,k]
            h_advec_thil[:,2*t+1] = h_advec_thil[:,2*t]        
        
        for t in range(ntimes):
             print time[t], h_advec_qt[:,t]
             print h_advec_thil[:,t]
        
    elif (time_method == 'gradient'):
        print 'Forcing can be interpolated in time since the forcing terms are assumed to follow a constant time-gradient.'
        
        ntimes = 2*n_files + 1
        time = np.zeros(ntimes)
        h_advec_thil = np.zeros((nlevs,ntimes),dtype=float)
        h_advec_qt = np.zeros((nlevs,ntimes),dtype=float)
        
        h_advec_qt[:,0] = 0.0
        h_advec_thil[:,0] = 0.0
        
        for t in range(n_files):
            time[2*t + 1] = 0.5*3600.0*time_dyn_hours[t]
            time[2*t + 2] = 3600.0*time_dyn_hours[t]
            
            h_advec_qt[:,2*t + 1] = dqvdt_adv_at_init_pres[t,:]
            for k in range(nlevs):
                h_advec_thil[k,2*t + 1] = (p0/state["pres"][k])**kappa*dtdt_adv_at_init_pres[t,k]
            
            #calculate gradient in time and extrapolate for time (2t + 2)
            for k in range(nlevs):
                grad = (h_advec_qt[k,2*t + 1] - h_advec_qt[k, 2*t])/(time[2*t + 1] - time[2*t])
                h_advec_qt[k,2*t + 2] = h_advec_qt[k,2*t+1] + grad*(time[2*t + 2] - time[2*t + 1])
                
                grad = (h_advec_thil[k,2*t + 1] - h_advec_thil[k, 2*t])/(time[2*t + 1] - time[2*t])
                h_advec_thil[k,2*t + 2] = h_advec_thil[k,2*t+1] + grad*(time[2*t + 2] - time[2*t + 1])
        
        for t in range(ntimes):
             print time[t], h_advec_qt[:,t]
             print h_advec_thil[:,t]
        
        for t in range(n_files):
            print t, dqvdt_adv_at_init_pres[t,:]
            print dtdt_adv_at_init_pres[t,:]
                    
    else:
        print 'Unrecognized forcing time method. Exiting.'
        exit()
        
    #time = np.zeros(ntimes)
    w_ls = np.zeros((nlevs,ntimes),dtype=float)
    omega = np.zeros((nlevs,ntimes),dtype=float)
    u_g = np.zeros((nlevs,ntimes),dtype=float)
    v_g = np.zeros((nlevs,ntimes),dtype=float)
    u_nudge = np.zeros((nlevs,ntimes),dtype=float)
    v_nudge = np.zeros((nlevs,ntimes),dtype=float)
    T_nudge = np.zeros((nlevs,ntimes),dtype=float)
    thil_nudge = np.zeros((nlevs,ntimes),dtype=float)
    qt_nudge = np.zeros((nlevs,ntimes),dtype=float)
    rad_heating = np.zeros((nlevs,ntimes),dtype=float)
    #h_advec_thil = np.zeros((nlevs,ntimes),dtype=float)
    v_advec_thil = np.zeros((nlevs,ntimes),dtype=float)
    #h_advec_qt = np.zeros((nlevs,ntimes),dtype=float)
    v_advec_qt = np.zeros((nlevs,ntimes),dtype=float)
    
    forcing = {
        "time": time,
        "w_ls": w_ls,
        "omega": omega,
        "u_g": u_g,
        "v_g": v_g,
        "u_nudge": u_nudge,
        "v_nudge": v_nudge,
        "T_nudge": T_nudge,
        "thil_nudge": thil_nudge,
        "qt_nudge": qt_nudge,
        "rad_heating": rad_heating,
        "h_advec_thil": h_advec_thil,
        "v_advec_thil": v_advec_thil,
        "h_advec_qt": h_advec_qt,
        "v_advec_qt": v_advec_qt
    }
    
    return forcing

def add_noahmp_coldstart(surface, date):
    """Add cold-start ICs for the NoahMP LSM from Noah LSM variables"""
    
    #use cold start section of FV3/io/FV3GFS_io.F90 to initialize NoahMP-specific variables (this is a python port of the Fortran code in that file)
    
    #MPTABLE.TBL uses a namelist format, so can use f90nml to read it in
    mptable_nml_all = f90nml.read(os.path.join(NOAHMP_TABLES_DIR, 'MPTABLE.TBL'))
    #MPTABLE.TBL contains data (with distinct namelists) for USGS and MODIS data; looks like MODIS is the operational
    mptable_nml_active = mptable_nml_all['noah_mp_modis_parameters'] #alternative is mptable_nml_all['noah_mp_usgs_parameters']
    
    #operational values; change if necessary (or read from somewhere?)
    n_snow_layers = 3
    n_soil_layers = 4
    
    #thickness of each soil level
    dzs = np.array([0.1,0.3,0.6,1.0])
    
    #bottom depth of each soil level
    zsoil = np.array([-0.1,-0.4,-1.0,-2.0])
    
    #initialize all NoahMP vars as missing
    surface["tvxy"]     = missing_value
    surface["tgxy"]     = missing_value
    surface["tahxy"]    = missing_value
    surface["canicexy"] = missing_value
    surface["canliqxy"] = missing_value
    surface["eahxy"]    = missing_value
    surface["cmxy"]     = missing_value
    surface["chxy"]     = missing_value
    surface["fwetxy"]   = missing_value
    surface["sneqvoxy"] = missing_value
    surface["alboldxy"] = missing_value
    surface["qsnowxy"]  = missing_value
    surface["wslakexy"] = missing_value
    surface["taussxy"]  = missing_value
    surface["waxy"]     = missing_value
    surface["wtxy"]     = missing_value
    surface["zwtxy"]    = missing_value
    surface["xlaixy"]   = missing_value
    surface["xsaixy"]   = missing_value

    surface["lfmassxy"] = missing_value
    surface["stmassxy"] = missing_value
    surface["rtmassxy"] = missing_value
    surface["woodxy"]   = missing_value
    surface["stblcpxy"] = missing_value
    surface["fastcpxy"] = missing_value
    surface["smcwtdxy"] = missing_value
    surface["deeprechxy"] = missing_value
    surface["rechxy"]   = missing_value

    surface["snowxy"]   = missing_value
    surface["snicexy"]  = np.ones(n_snow_layers)*missing_value
    surface["snliqxy"]  = np.ones(n_snow_layers)*missing_value
    surface["tsnoxy"]   = np.ones(n_snow_layers)*missing_value
    surface["smoiseq"]  = np.ones(n_soil_layers)*missing_value
    surface["zsnsoxy"]  = np.ones(n_snow_layers + n_soil_layers)*missing_value
    
    if surface["slmsk"] > 0.01:
        surface["tvxy"] = surface["T_surf"]
        surface["tgxy"] = surface["T_surf"]
        surface["tahxy"] = surface["T_surf"]
        
        if (surface["snwdph"] > 0.01 and surface["T_surf"] > 273.15 ):
            surface["tvxy"] = 273.15
            surface["tgxy"] = 273.15
            surface["tahxy"]= 273.15
            
        surface["canicexy"] = 0.0
        surface["canliqxy"] = surface["canopy"]
        surface["eahxy"]    = 2000.0
        
        #      eahxy = psfc*qv/(0.622+qv); qv is mixing ratio, converted from sepcific
        #      humidity specific humidity /(1.0 - specific humidity)
        
        surface["cmxy"]     = 0.0
        surface["chxy"]     = 0.0
        surface["fwetxy"]   = 0.0
        surface["sneqvoxy"] = surface["sheleg"]     # mm
        surface["alboldxy"] = 0.65
        surface["qsnowxy"]  = 0.0
        
        surface["wslakexy"] = 0.0
        surface["taussxy"]  = 0.0
        surface["waxy"]     = 4900.0
        surface["wtxy"]     = surface["waxy"]
        surface["zwtxy"]    = (25.0 + 2.0) - surface["waxy"] / 1000.0 /0.2
        
        vegtyp = np.int(surface['vtyp'])
        if (vegtyp == 0):
            vegtyp = 7
        if ((vegtyp == mptable_nml_active['ISBARREN']) or (vegtyp == mptable_nml_active['ISSNOW']) or  (vegtyp == mptable_nml_active['ISURBAN']) or (vegtyp == mptable_nml_active['ISWATER'])) :
            surface["xlaixy"] = 0.0
            surface["xsaixy"] = 0.0

            surface["lfmassxy"] = 0.0
            surface["stmassxy"] = 0.0
            surface["rtmassxy"] = 0.0

            surface["woodxy"] = 0.0       
            surface["stblcpxy"] = 0.0      
            surface["fastcpxy"] = 0.0
        else:
            #laim gives monthly values for each of the vegetation types
            laim = np.array(mptable_nml_active['LAIM']).reshape(12,20)
            
            #be sure to use month-1, vegtyp-1 since python is 0-indexed
            surface["xlaixy"] = np.amax([laim[date["month"]-1,vegtyp-1],0.05])
            surface["xsaixy"] = np.amax([surface["xlaixy"]*0.1,0.05])
            
            sla = np.array(mptable_nml_active['SLA'])
            masslai = 1000.0 / np.amax([sla[vegtyp-1],1.0])
            surface["lfmassxy"] = surface["xlaixy"]*masslai
            masssai = 1000.0 / 3.0
            surface["stmassxy"] = surface["xsaixy"]*masssai
            
            surface["rtmassxy"] = 500.0      

            surface["woodxy"] = 500.0       
            surface["stblcpxy"] = 1000.0      
            surface["fastcpxy"] = 1000.0
            
        if ( vegtyp == mptable_nml_active['ISSNOW'] ):
            for k in range(n_soil_layers):
                surface["stc"][k] = np.amin([surface["stc"][k],np.amin([surface["tg3"],263.15])])
                surface["smc"][k] = 1
                surface["slc"][k] = 0
        
        snd = surface["snwdph"]/1000.0  # go to m from snwdph
        
        if (surface["sheleg"] != 0.0 and snd == 0.0 ):
            snd = surface["sheleg"]/1000.0
            
        if (vegtyp == 15):                       # land ice in MODIS/IGBP
            if ( surface["sheleg"] < 0.1):
                surface["sheleg"] = 0.1
                snd = 0.01
        
        dzsno = np.zeros(n_snow_layers)
        if (snd < 0.025 ):
            surface["snowxy"] = 0.0
            dzsno[:]          = 0.0
        elif (snd >= 0.025 and snd <= 0.05 ):
            surface["snowxy"] = -1.0
            dzsno[-1]         = snd
        elif (snd > 0.05 and snd <= 0.10 ):
            surface["snowxy"] = -2.0
            dzsno[-2] = 0.5*snd
            dzsno[-1] = 0.5*snd
        elif (snd > 0.10 and snd <= 0.25 ):
            surface["snowxy"] = -2.0
            dzsno[-2] = 0.05
            dzsno[-1] = snd - 0.05
        elif (snd > 0.25 and snd <= 0.45 ):
            surface["snowxy"] = -3.0
            dzsno[-3] = 0.05
            dzsno[-2] = 0.5*(snd-0.05)
            dzsno[-1] = 0.5*(snd-0.05)
        elif (snd > 0.45): 
            surface["snowxy"] = -3.0
            dzsno[-3] = 0.05
            dzsno[-2] = 0.20
            dzsno[-1] = snd - 0.05 - 0.20
        else:
            message = 'problem with the logic assigning snow layers.'
            logging.critical(message)
            raise Exception(message)
        
        surface["tsnoxy"][:]  = 0.0
        surface["snicexy"][:] = 0.0
        surface["snliqxy"][:] = 0.0
        surface["zsnsoxy"][:] = 0.0
        
        isnow = np.int(surface["snowxy"] + n_snow_layers)
        dzsnso = np.zeros(n_snow_layers + n_soil_layers)
        for k in range(isnow, n_snow_layers):
            surface["tsnoxy"][k]  = surface["tgxy"]
            surface["snliqxy"][k] = 0.0
            surface["snicexy"][k] = 1.00 * dzsno[k] * surface["sheleg"]/snd  #this line causes a warning
            
            dzsnso[k] = -dzsno[k]
        
        for k in range(n_snow_layers, n_snow_layers + n_soil_layers):
            dzsnso[k] = -dzs[k - n_snow_layers]
        
        surface["zsnsoxy"][isnow] = dzsnso[isnow]
        for k in range(isnow+1,n_snow_layers + n_soil_layers):
            surface["zsnsoxy"][k] = surface["zsnsoxy"][k-1] + dzsnso[k]
        
        soilparm = read_noahmp_soil_table()
        
        soiltyp  = int(surface["styp"])
        if (soiltyp != 0):
            #find the index of the soiltype from the "index" field
            index = soilparm["index"].index(soiltyp)
            bexp   = soilparm["bb"][index]
            smcmax = soilparm["maxsmc"][index]
            smcwlt = soilparm["wltsmc"][index]
            dwsat  = soilparm["satdw"][index]
            dksat  = soilparm["satdk"][index]
            psisat = -soilparm["satpsi"][index]
        
        if (vegtyp == mptable_nml_active['ISURBAN']):
            smcmax = 0.45
            smcwlt = 0.40
        
        if ((bexp > 0.0) and (smcmax > 0.0) and (-psisat > 0.0 )):
            for k in range(n_soil_layers):
                if ( k == 0 ):
                    ddz = -zsoil[k+1] * 0.5
                elif ( k < n_soil_layers-1 ):
                    ddz = (zsoil[k-1] - zsoil[k+1] ) * 0.5
                else:
                    ddz = zsoil[k-1] - zsoil[k]
# !
# ! Use newton-raphson method to find eq soil moisture
# !
                expon = bexp +1.
                aa = dwsat/ddz
                bb = dksat / smcmax ** expon

                smc = 0.5 * smcmax
                for iter in range(100):
                    func = (smc - smcmax) * aa +  bb * smc ** expon
                    dfunc = aa + bb * expon * smc ** bexp
                    dx  = func/dfunc
                    smc = smc - dx
                    if ( abs (dx) < 1.e-6):
                        break

                surface["smoiseq"][k] = np.amin([np.amax([smc,1.e-4]),smcmax*0.99])
        else:
            surface["smoiseq"][:] = smcmax

        surface["smcwtdxy"]   = smcmax
        surface["deeprechxy"] = 0.0
        surface["rechxy"]     = 0.0
        
    return surface

def read_noahmp_soil_table():
    """Read values from SOILPARM.TBL for NoahMP LSM ICs"""
    #returns a dictionary with data
    
    #two different datasets are included in the table
    choices = ["STAS","STAS-RUC"]
    
    #get all lines of the file
    with open(os.path.join(NOAHMP_TABLES_DIR, 'SOILPARM.TBL'), 'r') as f:
        lineList = f.readlines()
    f.close()
    
    #find the line where the desired data starts 
    line_index = 0
    for line in lineList:
        line_index += 1
        #hardcoded to look for choices[0]; swap choices[0] for choices[1] to use choices[1] below
        m = re.match(choices[0],line) and not re.match(choices[1],line)
        if m:
            start_index = line_index
            break
    
    #get the data for each variable from the lines    
    n_soil_types = int(lineList[start_index].split()[0].split(',')[0])
    soil_index = []
    bb = []
    drysmc = []
    f11 = []
    maxsmc = []
    refsmc = []
    satpsi = []
    satdk = []
    satdw = []
    wltsmc = []
    qtz = []
    name = []
    for line in lineList[start_index+1:start_index+n_soil_types+1]:
        values = line.strip().split(',')
        soil_index.append(int(values[0]))
        bb.append(float(values[1]))
        drysmc.append(float(values[2]))
        f11.append(float(values[3]))
        maxsmc.append(float(values[4]))
        refsmc.append(float(values[5]))
        satpsi.append(float(values[6]))
        satdk.append(float(values[7]))
        satdw.append(float(values[8]))
        wltsmc.append(float(values[9]))
        qtz.append(float(values[10]))
        name.append(values[11].strip())
    
    soilparm = {
        "index": soil_index,
        "bb": bb,
        "drysmc": drysmc,
        "f11": f11,
        "maxsmc": maxsmc,
        "refsmc": refsmc,
        "satpsi": satpsi,
        "satdk": satdk,
        "satdw": satdw,
        "wltsmc": wltsmc,
        "qtz": qtz,
        "name": name        
    }
    
    return soilparm

def write_SCM_case_file(state, surface, oro, forcing, case, date):
    """Write all data to a netCDF file that the SCM can read"""
    #expects the data to write, the name of the generated file, and the date corresponding to the ICs
    
    real_type = np.float64
    int_type = np.int32
    
    nlevs = state["nlevs"]
    nsoil = len(surface["stc"])
    
    #find out if noahmp ICs have been generated
    noahmp = False
    if "snicexy" in surface.keys():
        noahmp = True
        nsnow = len(surface["snicexy"])
    
    nc_file = Dataset(os.path.join(PROCESSED_CASE_DIR, case + '.nc'), 'w', format='NETCDF4')
    nc_file.description = "FV3GFS model profile input (no forcing)"
    
    #create groups for scalars, intitialization, and forcing

    scalar_grp = nc_file.createGroup("scalars")
    initial_grp = nc_file.createGroup("initial")
    forcing_grp = nc_file.createGroup("forcing")
    
    #create dimensions and write them out

    time_dim = nc_file.createDimension('time', None)
    time_var = nc_file.createVariable('time', real_type, ('time',))
    time_var[:] = forcing["time"]
    time_var.units = 's'
    time_var.description = 'elapsed time since the beginning of the simulation'

    levels_dim = nc_file.createDimension('levels', None)
    levels_var = nc_file.createVariable('levels', real_type, ('levels',))
    levels_var[:] = state["pres"]
    levels_var.units = 'Pa'
    levels_var.description = 'pressure levels'
    
    soil_dim  = nc_file.createDimension('nsoil',None)
    soil_depth_var = nc_file.createVariable('soil_depth', real_type, ('nsoil',))
    soil_depth_var[:] = [0.1,0.4,1.0,2.0]
    soil_depth_var.units = 'm'
    soil_depth_var.description = 'depth of bottom of soil layers'
    
    if noahmp:
        snow_dim = nc_file.createDimension('nsnow',None)
        soil_plus_snow_dim = nc_file.createDimension('nsoil_plus_nsnow',None)
        
    #initial group

    temperature_var = initial_grp.createVariable('temp', real_type, ('levels',))
    temperature_var[:] = state["T"][0:nlevs]
    temperature_var.units = 'K'
    temperature_var.description = 'initial profile of absolute temperature'

    qt_var = initial_grp.createVariable('qt', real_type, ('levels',))
    qt_var[:] = state["qv"][0:nlevs]
    qt_var.units = 'kg kg^-1'
    qt_var.description = 'initial profile of total water specific humidity'

    ql_var = initial_grp.createVariable('ql', real_type, ('levels',))
    ql_var[:] = state["ql"][0:nlevs]
    ql_var.units = 'kg kg^-1'
    ql_var.description = 'initial profile of liquid water specific humidity'

    qi_var = initial_grp.createVariable('qi', real_type, ('levels',))
    qi_var[:] = 0.0
    qi_var.units = 'kg kg^-1'
    qi_var.description = 'initial profile of ice water specific humidity'

    u_var = initial_grp.createVariable('u', real_type, ('levels',))
    u_var[:] = state["u"][0:nlevs]
    u_var.units = 'm s^-1'
    u_var.description = 'initial profile of E-W horizontal wind'

    v_var = initial_grp.createVariable('v', real_type, ('levels',))
    v_var[:] = state["v"][0:nlevs]
    v_var.units = 'm s^-1'
    v_var.description = 'initial profile of N-S horizontal wind'

    tke_var = initial_grp.createVariable('tke', real_type, ('levels',))
    tke_var[:] = 0.0
    tke_var.units = 'm^2 s^-2'
    tke_var.description = 'initial profile of turbulence kinetic energy'

    ozone_var = initial_grp.createVariable('ozone', real_type, ('levels',))
    ozone_var[:] = state["o3"][0:nlevs]
    ozone_var.units = 'kg kg^-1'
    ozone_var.description = 'initial profile of ozone mass mixing ratio'
    
    stc_var = initial_grp.createVariable('stc',real_type,('nsoil',))
    stc_var[:] = surface['stc'][0:nsoil]
    stc_var.units = "K"
    stc_var.description = "initial profile of soil temperature"
    
    smc_var = initial_grp.createVariable('smc',real_type,('nsoil',))
    smc_var[:] = surface['smc'][0:nsoil]
    smc_var.units = "kg"
    smc_var.description = "initial profile of soil moisture"
    
    slc_var = initial_grp.createVariable('slc',real_type,('nsoil',))
    slc_var[:] = surface['slc'][0:nsoil]
    slc_var.units = "kg"
    slc_var.description = "initial profile of soil liquid moisture"
    
    if noahmp:
        snicexy_var = initial_grp.createVariable('snicexy',real_type,('nsnow',))
        snicexy_var[:] = surface['snicexy'][0:nsnow]
        snicexy_var.units = "mm"
        snicexy_var.description = "initial profile of snow layer ice"
        
        snliqxy_var = initial_grp.createVariable('snliqxy',real_type,('nsnow',))
        snliqxy_var[:] = surface['snliqxy'][0:nsnow]
        snliqxy_var.units = "mm"
        snliqxy_var.description = "initial profile of snow layer ice"
        
        tsnoxy_var = initial_grp.createVariable('tsnoxy',real_type,('nsnow',))
        tsnoxy_var[:] = surface['tsnoxy'][0:nsnow]
        tsnoxy_var.units = "K"
        tsnoxy_var.description = "initial profile of snow layer temperature"
        
        smoiseq_var = initial_grp.createVariable('smoiseq',real_type,('nsoil',))
        smoiseq_var[:] = surface['smoiseq'][0:nsoil]
        smoiseq_var.units = "m3 m-3"
        smoiseq_var.description = "initial profile of equilibrium soil water content"
        
        zsnsoxy_var = initial_grp.createVariable('zsnsoxy',real_type,('nsoil_plus_nsnow',))
        zsnsoxy_var[:] = surface['zsnsoxy'][0:nsoil + nsnow]
        zsnsoxy_var.units = "m"
        zsnsoxy_var.description = "layer bottom depth from snow surface"
    
    #forcing group

    p_surf_var = forcing_grp.createVariable('p_surf', real_type, ('time',))
    p_surf_var[:] = state["p_surf"]
    p_surf_var.units = 'Pa'
    p_surf_var.description = 'surface pressure'

    T_surf_var = forcing_grp.createVariable('T_surf', real_type, ('time',))
    T_surf_var[:] = surface["T_surf"]
    T_surf_var.units = 'K'
    T_surf_var.description = 'surface absolute temperature'

    w_ls_var = forcing_grp.createVariable('w_ls', real_type, ('levels','time',))
    w_ls_var[:] = forcing["w_ls"]
    w_ls_var.units = 'm s^-1'
    w_ls_var.description = 'large scale vertical velocity'
    
    omega_var = forcing_grp.createVariable('omega', real_type, ('levels','time',))
    omega_var[:] = forcing["omega"]
    omega_var.units = 'Pa s^-1'
    omega_var.description = 'large scale pressure vertical velocity'
    
    u_g_var = forcing_grp.createVariable('u_g', real_type, ('levels','time',))
    u_g_var[:] = forcing["u_g"]
    u_g_var.units = 'm s^-1'
    u_g_var.description = 'large scale geostrophic E-W wind'
    
    v_g_var = forcing_grp.createVariable('v_g', real_type, ('levels','time',))
    v_g_var[:] = forcing["v_g"]
    v_g_var.units = 'm s^-1'
    v_g_var.description = 'large scale geostrophic N-S wind'
    
    u_nudge_var = forcing_grp.createVariable('u_nudge', real_type, ('levels','time',))
    u_nudge_var[:] = forcing["u_nudge"]
    u_nudge_var.units = 'm s^-1'
    u_nudge_var.description = 'E-W wind to nudge toward'
    
    v_nudge_var = forcing_grp.createVariable('v_nudge', real_type, ('levels','time',))
    v_nudge_var[:] = forcing["v_nudge"]
    v_nudge_var.units = 'm s^-1'
    v_nudge_var.description = 'N-S wind to nudge toward'
    
    T_nudge_var = forcing_grp.createVariable('T_nudge', real_type, ('levels','time',))
    T_nudge_var[:] = forcing["T_nudge"]
    T_nudge_var.units = 'K'
    T_nudge_var.description = 'absolute temperature to nudge toward'
     
    thil_nudge_var = forcing_grp.createVariable('thil_nudge', real_type, ('levels','time',))
    thil_nudge_var[:] = forcing["thil_nudge"]
    thil_nudge_var.units = 'K'
    thil_nudge_var.description = 'potential temperature to nudge toward'
    
    qt_nudge_var = forcing_grp.createVariable('qt_nudge', real_type, ('levels','time',))
    qt_nudge_var[:] = forcing["qt_nudge"]
    qt_nudge_var.units = 'kg kg^-1'
    qt_nudge_var.description = 'q_t to nudge toward'
    
    rad_heating_var = forcing_grp.createVariable('dT_dt_rad', real_type, ('levels','time',))
    rad_heating_var[:] = forcing["rad_heating"]
    rad_heating_var.units = 'K s^-1'
    rad_heating_var.description = 'prescribed radiative heating rate'
    
    h_advec_thil_var = forcing_grp.createVariable('h_advec_thetail', real_type, ('levels','time',))
    h_advec_thil_var[:] = forcing["h_advec_thil"]
    h_advec_thil_var.units = 'K s^-1'
    h_advec_thil_var.description = 'prescribed theta_il tendency due to horizontal advection'
    
    v_advec_thil_var = forcing_grp.createVariable('v_advec_thetail', real_type, ('levels','time',))
    v_advec_thil_var[:] = forcing["v_advec_thil"]
    v_advec_thil_var.units = 'K s^-1'
    v_advec_thil_var.description = 'prescribed theta_il tendency due to vertical advection'
    
    h_advec_qt_var = forcing_grp.createVariable('h_advec_qt', real_type, ('levels','time',))
    h_advec_qt_var[:] = forcing["h_advec_qt"]
    h_advec_qt_var.units = 'kg kg^-1 s^-1'
    h_advec_qt_var.description = 'prescribed q_t tendency due to horizontal advection'
    
    v_advec_qt_var = forcing_grp.createVariable('v_advec_qt', real_type, ('levels','time',))
    v_advec_qt_var[:] = forcing["v_advec_qt"]
    v_advec_qt_var.units = 'kg kg^-1 s^-1'
    v_advec_qt_var.description = 'prescribed q_t tendency due to vertical advection'
    
    #scalar group
    year_var = scalar_grp.createVariable('init_year',int_type)
    year_var[:] = date["year"]
    year_var.units = "years"
    year_var.description = "year at time of initial values"
    
    month_var = scalar_grp.createVariable('init_month',int_type)
    month_var[:] = date["month"]
    month_var.units = "months"
    month_var.description = "month at time of initial values"
    
    day_var = scalar_grp.createVariable('init_day',int_type)
    day_var[:] = date["day"]
    day_var.units = "days"
    day_var.description = "day at time of initial values"
    
    hour_var = scalar_grp.createVariable('init_hour',int_type)
    hour_var[:] = date["hour"]
    hour_var.units = "hours"
    hour_var.description = "hour at time of initial values"
    
    minute_var = scalar_grp.createVariable('init_minute',int_type)
    minute_var[:] = date["minute"]
    minute_var.units = "minutes"
    minute_var.description = "minute at time of initial values"
    
    second_var = scalar_grp.createVariable('init_second',int_type)
    second_var[:] = 0.0
    second_var.units = "seconds"
    second_var.description = "second at time of initial values"
    
    lat_var = scalar_grp.createVariable('lat', real_type)
    lat_var[:] = surface["lat"]
    lat_var.units = 'degrees N'
    lat_var.description = 'latitude of column'

    lon_var = scalar_grp.createVariable('lon', real_type)
    lon_var[:] = surface["lon"]
    lon_var.units = 'degrees E'
    lon_var.description = 'longitude of column'
    
    area = scalar_grp.createVariable('area', real_type)
    area[:] = surface["area"]
    area.units = "m^2" 
    area.description = "grid cell area"
    
    #Noah initial parameters
    
    vegsrc  = scalar_grp.createVariable('vegsrc',int_type)
    vegsrc[:] = 1 #when would this be 2?
    vegsrc.description = "vegetation soure (1-2)"
    
    vegtyp  = scalar_grp.createVariable('vegtyp',int_type)
    vegtyp[:] = surface["vtyp"]
    vegtyp.description = "vegetation type (1-12)"

    soiltyp = scalar_grp.createVariable('soiltyp',int_type)
    soiltyp[:] = surface["styp"]
    soiltyp.description = "soil type (1-12)"
    
    slopetyp = scalar_grp.createVariable('slopetyp',int_type)
    slopetyp[:] = surface["slope"]
    slopetyp.description = "slope type (1-9)"
    
    vegfrac = scalar_grp.createVariable('vegfrac',real_type)
    vegfrac[:] = surface["vfrac"]
    vegfrac.description = "vegetation fraction"
    
    shdmin = scalar_grp.createVariable('shdmin',real_type)
    shdmin[:] = surface["shdmin"]
    shdmin.description = "minimum vegetation fraction"
    
    shdmax = scalar_grp.createVariable('shdmax',real_type)
    shdmax[:] = surface["shdmax"]
    shdmax.description = "maximum vegetation fraction"
    
    zorl = scalar_grp.createVariable('zorl',real_type)
    zorl[:] = surface["zorl"]
    zorl.units = "cm"
    zorl.description = "surface roughness length"
    
    islmsk = scalar_grp.createVariable('slmsk',real_type)
    islmsk[:] = surface["slmsk"]
    islmsk.description = "land-sea-ice mask"
    
    canopy = scalar_grp.createVariable('canopy',real_type)
    canopy[:] = surface["canopy"]
    canopy.units = "kg m-2"
    canopy.description = "amount of water stored in canopy"
    
    hice = scalar_grp.createVariable('hice',real_type)
    hice[:] = surface["hice"]
    hice.units = "m"
    hice.description = "sea ice thickness"
    
    fice = scalar_grp.createVariable('fice',real_type)
    fice[:] = surface["fice"]
    fice.description = "ice fraction"
    
    tisfc = scalar_grp.createVariable('tisfc',real_type)
    tisfc[:] = surface["tisfc"]
    tisfc.units = "K"
    tisfc.description = "ice surface temperature"
    
    snwdph = scalar_grp.createVariable('snwdph',real_type)
    snwdph[:] = surface["snwdph"]
    snwdph.units = "mm"
    snwdph.description = "water equivalent snow depth"
    
    snoalb = scalar_grp.createVariable('snoalb',real_type)
    snoalb[:] = surface["snoalb"]
    snoalb.description = "maximum snow albedo"
    
    sncovr = scalar_grp.createVariable('sncovr',real_type)
    sncovr[:] = 0.0
    sncovr.description = "snow area fraction"
        
    tg3 = scalar_grp.createVariable('tg3',real_type)
    tg3[:] = surface["tg3"]
    tg3.units = "K"  
    tg3.description = "deep soil temperature"
    
    uustar = scalar_grp.createVariable('uustar',real_type)
    uustar[:] = surface["uustar"]
    uustar.units = "m s-1"  
    uustar.description = "friction velocity"
    
    alvsf = scalar_grp.createVariable('alvsf',real_type)
    alvsf[:] = surface["alvsf"]
    alvsf.units = "None" 
    alvsf.description = "60 degree vis albedo with strong cosz dependency"
    
    alnsf = scalar_grp.createVariable('alnsf',real_type)
    alnsf[:] = surface["alnsf"]
    alnsf.units = "None"
    alnsf.description = "60 degree nir albedo with strong cosz dependency"
    
    alvwf = scalar_grp.createVariable('alvwf',real_type)
    alvwf[:] = surface["alvwf"]
    alvwf.units = "None"
    alvwf.description = "60 degree vis albedo with weak cosz dependency"
    
    alnwf = scalar_grp.createVariable('alnwf',real_type)
    alnwf[:] = surface["alnwf"]
    alnwf.units = "None"
    alnwf.description = "60 degree nir albedo with weak cosz dependency"
    
    facsf = scalar_grp.createVariable('facsf',real_type)
    facsf[:] = surface["facsf"]
    facsf.units = "None" 
    facsf.description = "fractional coverage with strong cosz dependency"
    
    facwf = scalar_grp.createVariable('facwf',real_type)
    facwf[:] = surface["facwf"]
    facwf.units = "None" 
    facwf.description = "fractional coverage with weak cosz dependency"
    
    #Orography initial parameters
    
    stddev = scalar_grp.createVariable('stddev',real_type)
    stddev[:] = oro["stddev"]
    stddev.units = "m"
    stddev.description = "standard deviation of subgrid orography"
    
    convexity = scalar_grp.createVariable('convexity',real_type)
    convexity[:] = oro["convexity"]
    convexity.units = ""
    convexity.description = "convexity of subgrid orography"
    
    oa1 = scalar_grp.createVariable('oa1',real_type)
    oa1[:] = oro["oa1"]
    oa1.units = ""
    oa1.description = "assymetry of subgrid orography 1"
    
    oa2 = scalar_grp.createVariable('oa2',real_type)
    oa2[:] = oro["oa2"]
    oa2.units = ""
    oa2.description = "assymetry of subgrid orography 2"
    
    oa3 = scalar_grp.createVariable('oa3',real_type)
    oa3[:] = oro["oa3"]
    oa3.units = ""
    oa3.description = "assymetry of subgrid orography 3"
    
    oa4 = scalar_grp.createVariable('oa4',real_type)
    oa4[:] = oro["oa4"]
    oa4.units = ""
    oa4.description = "assymetry of subgrid orography 4"
    
    ol1 = scalar_grp.createVariable('ol1',real_type)
    ol1[:] = oro["ol1"]
    ol1.units = ""
    ol1.description = "fraction of grid box with subgrid orography higher than critical height 1"
    
    ol2 = scalar_grp.createVariable('ol2',real_type)
    ol2[:] = oro["ol2"]
    ol2.units = ""
    ol2.description = "fraction of grid box with subgrid orography higher than critical height 2"
    
    ol3 = scalar_grp.createVariable('ol3',real_type)
    ol3[:] = oro["ol3"]
    ol3.units = ""
    ol3.description = "fraction of grid box with subgrid orography higher than critical height 3"
    
    ol4 = scalar_grp.createVariable('ol4',real_type)
    ol4[:] = oro["ol4"]
    ol4.units = ""
    ol4.description = "fraction of grid box with subgrid orography higher than critical height 4"
    
    theta = scalar_grp.createVariable('theta',real_type)
    theta[:] = oro["theta"]
    theta.units = "deg"
    theta.description = "angle with respect to east of maximum subgrid orographic variations"
    
    gamma = scalar_grp.createVariable('gamma',real_type)
    gamma[:] = oro["gamma"]
    gamma.units = ""
    gamma.description = "anisotropy of subgrid orography"
    
    sigma = scalar_grp.createVariable('sigma',real_type)
    sigma[:] = oro["sigma"]
    sigma.units = ""
    sigma.description = "slope of subgrid orography"
    
    elvmax = scalar_grp.createVariable('elvmax',real_type)
    elvmax[:] = oro["elvmax"]
    elvmax.units = "m"
    elvmax.description = "maximum of subgrid orography"
    
    #NoahMP initial scalar parameters
    if noahmp:
        tvxy = scalar_grp.createVariable('tvxy',real_type)
        tvxy[:] = surface["tvxy"]
        tvxy.units = "K"
        tvxy.description = "vegetation temperature"
        
        tgxy = scalar_grp.createVariable('tgxy',real_type)
        tgxy[:] = surface["tgxy"]
        tgxy.units = "K"
        tgxy.description = "ground temperature for NoahMP"
        
        tahxy = scalar_grp.createVariable('tahxy',real_type)
        tahxy[:] = surface["tahxy"]
        tahxy.units = "K"
        tahxy.description = "canopy air temperature"
        
        canicexy = scalar_grp.createVariable('canicexy',real_type)
        canicexy[:] = surface["canicexy"]
        canicexy.units = "mm"
        canicexy.description = "canopy intercepted ice mass"
        
        canliqxy = scalar_grp.createVariable('canliqxy',real_type)
        canliqxy[:] = surface["canliqxy"]
        canliqxy.units = "mm"
        canliqxy.description = "canopy intercepted liquid water"
        
        eahxy = scalar_grp.createVariable('eahxy',real_type)
        eahxy[:] = surface["eahxy"]
        eahxy.units = "Pa"
        eahxy.description = "canopy air vapor pressure"
        
        cmxy = scalar_grp.createVariable('cmxy',real_type)
        cmxy[:] = surface["cmxy"]
        cmxy.units = ""
        cmxy.description = "surface drag coefficient for momentum for NoahMP"        
        
        chxy = scalar_grp.createVariable('chxy',real_type)
        chxy[:] = surface["chxy"]
        chxy.units = ""
        chxy.description = "surface exchange coeff heat & moisture for NoahMP"
    
        fwetxy = scalar_grp.createVariable('fwetxy',real_type)
        fwetxy[:] = surface["fwetxy"]
        fwetxy.units = ""
        fwetxy.description = "area fraction of canopy that is wetted/snowed"
        
        sneqvoxy = scalar_grp.createVariable('sneqvoxy',real_type)
        sneqvoxy[:] = surface["sneqvoxy"]
        sneqvoxy.units = "mm"
        sneqvoxy.description = "snow mass at previous time step"
        
        alboldxy = scalar_grp.createVariable('alboldxy',real_type)
        alboldxy[:] = surface["alboldxy"]
        alboldxy.units = ""
        alboldxy.description = "snow albedo at previous time step"
        
        qsnowxy = scalar_grp.createVariable('qsnowxy',real_type)
        qsnowxy[:] = surface["qsnowxy"]
        qsnowxy.units = "mm s-1"
        qsnowxy.description = "snow precipitation rate at surface"
        
        wslakexy = scalar_grp.createVariable('wslakexy',real_type)
        wslakexy[:] = surface["wslakexy"]
        wslakexy.units = "mm"
        wslakexy.description = "lake water storage"
        
        taussxy = scalar_grp.createVariable('taussxy',real_type)
        taussxy[:] = surface["taussxy"]
        taussxy.units = ""
        taussxy.description = "non-dimensional snow age"
        
        waxy = scalar_grp.createVariable('waxy',real_type)
        waxy[:] = surface["waxy"]
        waxy.units = "mm"
        waxy.description = "water storage in aquifer"
        
        wtxy = scalar_grp.createVariable('wtxy',real_type)
        wtxy[:] = surface["wtxy"]
        wtxy.units = "mm"
        wtxy.description = "water storage in aquifer and saturated soil"
    
        zwtxy = scalar_grp.createVariable('zwtxy',real_type)
        zwtxy[:] = surface["zwtxy"]
        zwtxy.units = "m"
        zwtxy.description = "water table depth"
        
        xlaixy = scalar_grp.createVariable('xlaixy',real_type)
        xlaixy[:] = surface["xlaixy"]
        xlaixy.units = ""
        xlaixy.description = "leaf area index"
        
        xsaixy = scalar_grp.createVariable('xsaixy',real_type)
        xsaixy[:] = surface["xsaixy"]
        xsaixy.units = ""
        xsaixy.description = "stem area index"

        lfmassxy = scalar_grp.createVariable('lfmassxy',real_type)
        lfmassxy[:] = surface["lfmassxy"]
        lfmassxy.units = "g m-2"
        lfmassxy.description = "leaf mass"
        
        stmassxy = scalar_grp.createVariable('stmassxy',real_type)
        stmassxy[:] = surface["stmassxy"]
        stmassxy.units = "g m-2"
        stmassxy.description = "stem mass"
        
        rtmassxy = scalar_grp.createVariable('rtmassxy',real_type)
        rtmassxy[:] = surface["rtmassxy"]
        rtmassxy.units = "g m-2"
        rtmassxy.description = "fine root mass"
        
        woodxy = scalar_grp.createVariable('woodxy',real_type)
        woodxy[:] = surface["woodxy"]
        woodxy.units = "g m-2"
        woodxy.description = "wood mass including woody roots"
        
        stblcpxy = scalar_grp.createVariable('stblcpxy',real_type)
        stblcpxy[:] = surface["stblcpxy"]
        stblcpxy.units = "g m-2"
        stblcpxy.description = "stable carbon in deep soil"
        
        fastcpxy = scalar_grp.createVariable('fastcpxy',real_type)
        fastcpxy[:] = surface["fastcpxy"]
        fastcpxy.units = "g m-2"
        fastcpxy.description = "short-lived carbon in shallow soil"
    
        smcwtdxy = scalar_grp.createVariable('smcwtdxy',real_type)
        smcwtdxy[:] = surface["smcwtdxy"]
        smcwtdxy.units = "m3 m-3"
        smcwtdxy.description = "soil water content between the bottom of the soil and the water table"
        
        deeprechxy = scalar_grp.createVariable('deeprechxy',real_type)
        deeprechxy[:] = surface["deeprechxy"]
        deeprechxy.units = "m"
        deeprechxy.description = "recharge to or from the water table when deep"
        
        rechxy = scalar_grp.createVariable('rechxy',real_type)
        rechxy[:] = surface["rechxy"]
        rechxy.units = "m"
        rechxy.description = "recharge to or from the water table when shallow"
        
        snowxy = scalar_grp.createVariable('snowxy',real_type)
        snowxy[:] = surface["snowxy"]
        snowxy.units = ""
        snowxy.description = "number of snow layers"
    
    nc_file.close()

def main():
    setup_logging()
    
    #read in arguments
    (location, indices, date, in_dir, grid_dir, forcing_dir, tile, area, noahmp, case_name, old_chgres) = parse_arguments()
        
    #find tile containing the point using the supergrid if no tile is specified 
    if not tile:
        tile = find_tile(location, grid_dir)
        if tile < 0:
            message = 'No tile was found for location {0}'.format(location)
            logging.critical(message)
            raise Exception(message)
        print 'Tile found: {0}'.format(tile)
    
    #find index of closest point in the tile if indices are not specified
    if not indices:
        (tile_i, tile_j, point_lon, point_lat, dist_min) = find_loc_indices(location, in_dir, tile)
        print 'The closest point in tile {0} has indices [{1},{2}]'.format(tile,tile_i,tile_j)
        print 'This index has a central longitude/latitude of [{0},{1}]'.format(point_lon,point_lat)
        print 'This grid cell is approximately {0} km away from the desired location of {1} {2}'.format(dist_min/1.0E3,location[0],location[1])
    else:
        tile_i = indices[0]
        tile_j = indices[1]
        #still need to grab the lon/lat if the tile and indices are supplied
        (point_lon, point_lat) = find_lon_lat_of_indices(indices, in_dir, tile)
        
        print 'This index has a central longitude/latitude of [{0},{1}]'.format(point_lon,point_lat)
    
    #get UFS IC data (TODO: flag to read in RESTART data rather than IC data and implement different file reads)
    (state_data, surface_data, oro_data) = get_UFS_IC_data(in_dir, forcing_dir, tile, tile_i, tile_j, old_chgres)
    
    #cold start NoahMP variables
    if (noahmp):
        surface_data = add_noahmp_coldstart(surface_data, date)
    
    #get grid cell area if not given
    if not area:
        area = get_UFS_grid_area(grid_dir, tile, tile_i, tile_j)
    surface_data["area"] = area
    
    surface_data["lon"] = point_lon
    surface_data["lat"] = point_lat
        
    #get UFS forcing data (zeros for now; only placeholder)
    forcing_data = get_UFS_forcing_data(state_data["nlevs"], state_data, forcing_dir, tile, tile_i, tile_j)
    
    #write SCM case file
    write_SCM_case_file(state_data, surface_data, oro_data, forcing_data, case_name, date)
    
    
if __name__ == '__main__':
    main()
