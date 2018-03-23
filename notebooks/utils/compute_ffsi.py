import rasterio as rio
import pcraster_utils as pcru
import numpy as np
import pcraster as pcr
import glob
import subprocess
import os
import json

def get_path(path_format, id):
    files = glob.glob(path_format.format(id))
    assert(len(files) == 1)

    return files[0]

def convert2tif(input_path, output_path):
    cmd = 'rio convert {0} {1} --co COMPRESS=DEFLATE'.format(input_path, output_path)
    subprocess.check_call(cmd, shell=True)

def warp(input_path, output_path, template_path):
    cmd = 'rio warp {0} {1} --like {2} --resampling cubic'.format(input_path, output_path, template_path)
    subprocess.check_call(cmd, shell=True)
    
def read(path):
    img = rio.open(path)
    # print(path + ': ' + str(img.get_nodatavals()[0]))
    return img.read()[0]

import gc

def get_hist(a, range=None):
    aa = pcr.pcr_as_numpy(a)
    h = np.histogram(aa[~np.isnan(aa)], bins=200, range=range)
    return {'frequency':h[0].tolist(), 'value':h[1].tolist()}

def compute_FFSI(id, compute_hist):
    global histograms
    
    print(id)
    
    path_ldd = get_path('../output/continents/ldd/*{0}*.tif', id)
    path_dem = get_path('../output/continents/dem/*{0}*.tif', id)
    path_uparea = get_path('../output/continents/fa/*{0}*.tif', id)
    path_hand = get_path('../output/continents/hand-1000/*{0}*.tif', id)
    path_dist = get_path('../output/continents/dist-1000/*{0}*.tif', id)
    path_soil_depth = '../temp/{0}_FirstZoneCapacity.tif'.format(id)
    path_soil_porosity = '../temp/{0}_thetaS.tif'.format(id)
    path_soil_ksat = '../temp/{0}_FirstZoneKsatVer.tif'.format(id)    
    
    # clip top soil layer properties to DEM
    path_soil_depth_full = '../shared/soil/FirstZoneCapacity.tif'
    path_soil_porosity_full = '../shared/soil/thetaS.tif'
    path_soil_ksat_full = '../shared/soil/FirstZoneKsatVer.tif'

    warp(path_soil_depth_full, path_soil_depth, path_dem)
    warp(path_soil_porosity_full, path_soil_porosity, path_dem)
    warp(path_soil_ksat_full, path_soil_ksat, path_dem)
    
    # read top soil layer properties
    soil_depth = read(path_soil_depth)
    soil_porosity = read(path_soil_porosity)
    soil_ksat = read(path_soil_ksat)

    # read ldd, uparea, hand, dist
    ldd = read(path_ldd)
    dem = read(path_dem)
    uparea = read(path_uparea)
    hand = read(path_hand)
    dist = read(path_dist)
    
    pcru.initialize(path_ldd)
    
    scale = 30. # scale in meters
    
    ranges = {'HAND': [0,800], 'DIST':[0,3000], 'UP_AREA': [0, 12], 'UP_SLOPE': [0, 1], 'SOIL_DEPTH': [0, 1300], 'SOIL_INF': [0, 20]}

    print('compute_hist: ' + str(compute_hist))

    if compute_hist == True:
        print('Computing histograms ...')
        (s_hnd, s_dst, s_upstr, s_ustrslope, s_soildhaz, s_soilinfhaz, s_ffsi) \
           = pcru.computeFFSI(dem, ldd, uparea, dist, hand, soil_depth, soil_ksat, soil_porosity, scale, ranges, False)
    
        hist = { \
                'HAND': get_hist(s_hnd, tuple(ranges['HAND'])), \
                'DIST': get_hist(s_dst, tuple(ranges['DIST'])), \
                'UP_AREA': get_hist(s_upstr, tuple(ranges['UP_AREA'])), \
                'UP_SLOPE': get_hist(s_ustrslope, tuple(ranges['UP_SLOPE'])), \
                'SOIL_DEPTH': get_hist(s_soildhaz, tuple(ranges['SOIL_DEPTH'])), \
                'SOIL_INF': get_hist(s_soilinfhaz, tuple(ranges['SOIL_INF'])), \
                'FFSI': get_hist(s_ffsi), \
              }

        with open('../examples/FFSI/Afganistan/output/histograms/' + id + '_hist.json', 'w') as outfile:
            json.dump(hist, outfile)

    else:
        (s_hnd, s_dst, s_upstr, s_ustrslope, s_soildhaz, s_soilinfhaz, s_ffsi) \
          = pcru.computeFFSI(dem, ldd, uparea, dist, hand, soil_depth, soil_ksat, soil_porosity, scale, ranges, True)

        def save(name, v):
            map_path = '../examples/FFSI/Afganistan/output/catchments/' + name + '_{0}.map'.format(id)
            pcr.report(v, map_path)
    
            tif_path = '../examples/FFSI/Afganistan/output/catchments/' + name + '_{0}.tif'.format(id)
            print('Saving: ' + tif_path + ' ....')
            convert2tif(map_path, tif_path)
    
            os.remove(map_path)

        save('HAND', s_hnd)
        save('DIST', s_dst)
        save('UP_AREA', s_upstr)
        save('UP_SLOPE', s_ustrslope)
        save('SOIL_DEPTH', s_soildhaz)
        save('SOIL_INF', s_soildhaz)
	save('FFSI', s_ffsi)
    
    os.remove(path_soil_depth)
    os.remove(path_soil_porosity)
    os.remove(path_soil_ksat)
    
def compute_all(compute_histograms):
    ids = file('../examples/FFSI/Afganistan/ids.txt', 'r').read().splitlines()
    print(len(ids))
    for id, id in enumerate(ids):
        print(id)

        cmd = r'python utils/compute_ffsi.py --catchment_id=' + id + ' --compute_histogram=' + str(compute_histograms)
        print(cmd)
        subprocess.check_call(cmd, shell=True)
    
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description = 'Computes histogram and rasters related to FFSI (flash flood susceptibility index).')

    parser.add_argument('--catchment_id', nargs = '?', help = 'id of the catchment (used to search pre-computed HAND, DEM, FA)', required = False)
    parser.add_argument('--compute_histograms', nargs = '?', help = 'only compute histogram', required = False)

    args = parser.parse_args()

    if(args.catchment_id):
        compute_FFSI(args.catchment_id, args.compute_histograms)
    else:
        compute_all(args.compute_histograms)

