import os
import time
import json
import webbrowser

import shapely.wkt

from osgeo import ogr
from osgeo import gdal

# gdal.SetConfigOption('CPL_DEBUG', 'ON')
gdal.SetConfigOption('CPL_DEBUG', 'OFF')

class OAuth2(object):
    def __init__(self):
        self._scope = 'https://www.googleapis.com/auth/fusiontables'
        self._config_path = os.path.expanduser('~/.config/ogr2ft/credentials')

    def get_refresh_token(self):
        try:
            refresh_token = json.load(open(self._config_path))['refresh_token']
        except IOError:
            return self._request_refresh_token()

        return refresh_token

    def _request_refresh_token(self):
        # create configuration file dir
        config_dir = os.path.dirname(self._config_path)
        if not os.path.isdir(config_dir):
            os.makedirs(config_dir)

        # open browser and ask for authorization
        auth_request_url = gdal.GOA2GetAuthorizationURL(self._scope)
        print('Authorize access to your Fusion Tables, and paste the resulting code below: ' + auth_request_url)
        # webbrowser.open_new(auth_request_url)

        auth_code = raw_input('Please enter authorization code: ').strip()

        refresh_token = gdal.GOA2GetRefreshToken(auth_code, self._scope)

        # save it
        json.dump({'refresh_token': refresh_token}, open(self._config_path, 'w'))

        return refresh_token


def copy_features(src_layer, dst_layer, fix_geometry, simplify_geometry, start_index, total, batch_size):
    index = 0
    index_batch = 0
    for feat in src_layer:
        if index < start_index:
            index = index + 1
            continue

        try:
            geom = shapely.wkt.loads(feat.GetGeometryRef().ExportToWkt())
        except Exception as e:
            print('Error({0}), skipping geometry.'.format(e))
            continue

        if fix_geometry and not geom.is_valid:
            geom = geom.buffer(0.0)

        if simplify_geometry:
            geom = geom.simplify(0.004)

        f = ogr.Feature(dst_layer.GetLayerDefn())

        # print('Adding feature ...')

        # set field values
        for i in range(feat.GetFieldCount()):
            fd = feat.GetFieldDefnRef(i)
            f.SetField(fd.GetName(), feat.GetField(fd.GetName()))
            print('{0}: {1}'.format(fd.GetName(), feat.GetField(fd.GetName())))

        # set geometry 
        g = ogr.CreateGeometryFromWkt(geom.to_wkt())   
        f.SetGeometry(g)

        if index_batch == 0:
            dst_layer.StartTransaction()

        # create feature
        feature = dst_layer.CreateFeature(f)

        f.Destroy()

        index_batch = index_batch + 1

        if index_batch >= batch_size or index == total - 1:
            dst_layer.CommitTransaction()
            count = dst_layer.GetFeatureCount() # update number of inserted features
            print('Inserted {0} of {1} features ({2:.2f}%)'.format(count, total, 100. * float(count) / total))

            index_batch = 0

            if index == total - 1:
                break

        index = index + 1

def _get_ft_ds():
    refresh_token = OAuth2().get_refresh_token()
    ft_driver = ogr.GetDriverByName('GFT')
    print(refresh_token)
    return ft_driver.Open('GFT:refresh=' + refresh_token, True)

def convert(input_file, output_fusion_table, batch_size, add_missing=False, append=False):
    dst_ds = _get_ft_ds()

    src_ds = ogr.Open(input_file)
    src_layer = src_ds.GetLayerByIndex(0)

    gdal.UseExceptions() # avoid ERROR 1: ...
    try:
        dst_layer = dst_ds.GetLayerByName(output_fusion_table)
    except RuntimeError:
        pass
    gdal.DontUseExceptions() # avoid ERROR 1: ...

    is_new = False
    if dst_layer:
        if not add_missing and not append:
            print('Error: feature table already exists: ' + output_fusion_table + ', exiting ...')
            print('Use --add-missing to insert missing features')
            return
 
        total = src_layer.GetFeatureCount()
        count = dst_layer.GetFeatureCount()
        if append:
            total = total + count
    
        print('Warning: feature table already exists: ' + output_fusion_table)
        if count == total:
            print('All done, exiting ...')
        else:
            print('Inserting missing ' + str(total - count) + ' of ' + str(total) + ' features ...')
    else:
        print('Creating Fusion Table: ' + output_fusion_table)

        # create new layer and copy schema
        dst_layer = dst_ds.CreateLayer(output_fusion_table)
        if '.kml' in input_file:  
            f = src_layer.GetFeature(1) # bug?
        else:
            f = src_layer.GetFeature(0)
        [dst_layer.CreateField(f.GetFieldDefnRef(i)) for i in range(f.GetFieldCount())]
        is_new = True

    # copy features, retry during crashes
    fix_geometry = True
    simplify_geometry = False

    # re-open source layer, otherwise src_layer.GetFeature(1) seems to ifluence iterator in copy_features ?!?
    src_ds.Destroy()
    src_ds = ogr.Open(input_file)
    src_layer = src_ds.GetLayerByIndex(0)

    total = src_layer.GetFeatureCount()


    if is_new:  
        count = 0
    else:
        count = dst_layer.GetFeatureCount()

    while count < total:
        try:
            copy_features(src_layer, dst_layer, fix_geometry, simplify_geometry, count, total, batch_size)
            time.sleep(2)  # bad, is there a better way to wait until fusion table updates are finished?
            count = dst_layer.GetFeatureCount()
        except RuntimeError:
            time.sleep(2)  # bad, is there a better way to wait until fusion table updates are finished?
            count = dst_layer.GetFeatureCount() # update number of inserted features
            print('Retrying, {0} ({1:.2f}%)'.format(count, 100. * float(count) / total))

    src_ds.Destroy()
    dst_ds.Destroy()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Uploads a given feature collection to Google Fusion Table.')

    parser.add_argument('-i', '--input-file', help='input feature source (KML, SHP, SpatiLite, etc.)', required=True)
    parser.add_argument('-o', '--output-fusion-table', help='output Fusion Table name', required=True)
    parser.add_argument('-a', '--add-missing', help='add missing features from the last inserted feature index', action='store_true', required=False, default=False)
    parser.add_argument('-p', '--append', help='append features', action='store_true', required=False, default=False)
    parser.add_argument('-b', '--batch-size', help='number of records to insert at once', required=False)

    args = parser.parse_args()

    if args.batch_size:
        batch_size = int(args.batch_size)
    else:
        batch_size = 200

    convert(args.input_file, args.output_fusion_table, batch_size, args.add_missing, args.append)
