import pcraster as pcr
import numpy as np
import subprocess

def lattometres(lat):
    """"
    Determines the length of one degree lat/long at a given latitude (in meter).
    Code taken from http:www.nga.mil/MSISiteContent/StaticFiles/Calculators/degree.html
    Input: map with lattitude values for each cell
    Returns: length of a cell lat, length of a cell long
    """
    # radlat = spatial(lat * ((2.0 * math.pi)/360.0))
    # radlat = lat * (2.0 * math.pi)/360.0
    radlat = pcr.spatial(lat)  # pcraster cos/sin work in degrees!

    m1 = 111132.92  # latitude calculation term 1
    m2 = -559.82  # latitude calculation term 2
    m3 = 1.175  # latitude calculation term 3
    m4 = -0.0023  # latitude calculation term 4
    p1 = 111412.84  # longitude calculation term 1
    p2 = -93.5  # longitude calculation term 2
    p3 = 0.118  # longitude calculation term 3
    # # Calculate the length of a degree of latitude and longitude in meters

    latlen = m1 + (m2 * pcr.cos(2.0 * radlat)) + (m3 * pcr.cos(4.0 * radlat)) + (m4 * pcr.cos(6.0 * radlat))
    longlen = (p1 * pcr.cos(radlat)) + (p2 * pcr.cos(3.0 * radlat)) + (p3 * pcr.cos(5.0 * radlat))

    return latlen, longlen


def detRealCellLength(ZeroMap, sizeinmetres):
    """
    Determine cellength. Always returns the length
    in meters.
    """

    if sizeinmetres:
        reallength = pcr.celllength()
        xl = pcr.celllength()
        yl = pcr.celllength()
    else:
        aa = pcr.ycoordinate(pcr.boolean(pcr.cover(ZeroMap + 1, 1)))
        yl, xl = lattometres(aa)

        xl = xl * pcr.celllength()
        yl = yl * pcr.celllength()
        # Average length for surface area calculations. 

        reallength = (xl + yl) * 0.5

    return xl, yl, reallength


def norm(x, min_custom = None, max_custom = None):
    mmin = pcr.mapminimum(x)
    mmax = pcr.mapmaximum(x)
    
    if min_custom:
        mmin = min_custom
    
    if max_custom:
        mmax = max_custom

    if mmax - mmin == 0:
        return x * 0
    else:
        return (pcr.ifthenelse(x > mmax, mmax, pcr.ifthenelse(x < mmin, mmin, x)) - mmin) / (mmax - mmin)
    
def showmap(map, mtitle='Map'):
    import matplotlib.pyplot as plt

    plt.imshow(pcr.pcr_as_numpy(map))
    plt.title(mtitle)
    plt.colorbar()

def toMap(img, t, missing):
    if type(img) is np.ndarray:
        return pcr.numpy2pcr(t, img, missing)
   
    assert(type(img) is pcr._pcraster.Field)

    return img



def initialize(path):
    """
    Initializes pcraster by setting clonemap
    """
    
    clonepath = '../temp/pcraster_utils_clone.map'
    cmd = 'gdal_translate -a_nodata 0 -of PCRaster -ot Float32 ' + path + ' ' + clonepath
    subprocess.check_call(cmd, shell=True)

    pcr.setclone(clonepath)


def computeFFSI(dem, ldd, uparea, dist, hand, soil_depth, soil_ksat, soil_poros, scale, ranges, normalized):
    """
    Cmputes Flash Flood Suceptibility Index
    """

    depth = toMap(soil_depth, pcr.Scalar, -3.40282346639e+38)
    ksat = toMap(soil_ksat, pcr.Scalar, -3.40282346639e+38)
    poros = toMap(soil_poros, pcr.Scalar, -3.40282346639e+38)
    
    dem = toMap(dem, pcr.Scalar, -9999)
    ldd = toMap(ldd, pcr.Ldd, 255)
    uparea = toMap(uparea, pcr.Scalar, -3.40282346639e+38)
    dst = toMap(dist, pcr.Scalar, -3.40282346639e+38)
    hnd = toMap(hand, pcr.Scalar, -3.40282346639e+38)
    depth = toMap(depth, pcr.Scalar, -3.40282346639e+38)
    ksat = toMap(ksat, pcr.Scalar, -3.40282346639e+38)
    poros = toMap(poros, pcr.Scalar, -3.40282346639e+38)

    f1 = 0.8  # Weight of hand in the cost parameter
    f2 = 0.1  # Weight of distance in the cost parameter
    
    f3 = 0.4  # Weight of upstream area in the upstream hazzard
    f4 = 0.6  # Weight of upstream slope in the upstream hazzard
    
    f5 = 0.4  # Weight of soildepth in the upstream soil hazzard
    f6 = 0.6  # Weight of soilinfiltrationcapacity in the upstream soil hazzard

    f7 = 0.95  # Weight of upstream hazzard in the index
    f8 = 0.05  # Weight of upstream soil hazzard in the index
    
    x, y, rl = detRealCellLength(dem, 0)
    dst = dst * rl / pcr.celllength()

    raw_hnd = hnd
    raw_dst = dst
  
    # normalize hand and distance
    hnd = norm(hnd, ranges['HAND'][0], ranges['HAND'][1])
    dst = norm(dst, ranges['DIST'][0], ranges['DIST'][1])
    
    cost = hnd * f1 + dst * f2
    cost = norm(cost)

    # remove see stuf (depth = 0) from maps
    depth = pcr.ifthenelse(depth <= 0.0001, 500, depth)
    ksat = pcr.ifthenelse(ksat <= 0.0001, 100, ksat)
    
    poros = pcr.ifthenelse(poros <= 0.0001, 0.4, poros)
    
    # soil depth hazard
    soildhaz = pcr.max(0.0, depth * poros - 100)
    raw_soildhaz = soildhaz
    soildhaz = 1 - norm(soildhaz, ranges['SOIL_DEPTH'][0], ranges['SOIL_DEPTH'][1])
    
    # infiltration hazard
    soilinfhaz = pcr.max(0.0, 100 - ksat)
    raw_soilinfhaz = soilinfhaz

    soilinfhaz = norm(soilinfhaz, ranges['SOIL_INF'][0], ranges['SOIL_INF'][1])
    
    # soil hazard
    soilhaz = (f5 * soildhaz) + (soilinfhaz * f6)
    soilhaz = norm(soilhaz)
    
    # comulative (up) soil hazard
    raw_soilhazupstr = pcr.catchmenttotal(soilhaz, ldd) / uparea
    soilhazupstr = norm(raw_soilhazupstr)

    # upstream are maxed at 100km^2
    maxupstr = 100. * (scale * scale)  # 100 sqr km
    upstr = pcr.ln(pcr.min(maxupstr, uparea * rl * rl))
    raw_upstr = upstr
    upstr = norm(upstr, ranges['UP_AREA'][0], ranges['UP_AREA'][1])

    slope = pcr.slope(dem)
    slope = pcr.max(0.00001, slope * pcr.celllength() / rl)
    
    ustrslope = pcr.catchmenttotal(slope, ldd) / uparea
    raw_ustrslope = ustrslope
    ustrslope = norm(ustrslope, ranges['UP_SLOPE'][0], ranges['UP_SLOPE'][1])
    
    # more weigth to upstr -> river flooding, more weigth to slope, flash flooding
    upstrhaz = (f3 * upstr) + (f4 * ustrslope)
    upstrhaz = norm(upstrhaz)
    
    ffsi = (upstrhaz * f7 + soilhazupstr * f8) * (1.0 - cost)
    ffsi = norm(ffsi)

    # idx = pcr.ifthenelse(ffsi > 0.49, pcr.scalar(1),
    #                     pcr.ifthenelse(ffsi > 0.41, pcr.scalar(2),
    #                     pcr.ifthenelse(ffsi > 0.3,
    #                     pcr.scalar(3),
    #                     pcr.scalar(4))))
     
    if normalized:
        return hnd, dst, upstr, ustrslope, soildhaz, soilinfhaz, ffsi    
    else:
        return raw_hnd, raw_dst, raw_upstr, raw_ustrslope, raw_soildhaz, raw_soilinfhaz, ffsi    

        
