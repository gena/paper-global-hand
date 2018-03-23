import os
import time
import json
import webbrowser

import shapely.wkt

from osgeo import ogr
from osgeo import gdal

gdal.SetConfigOption('CPL_DEBUG', 'ON')
# gdal.SetConfigOption('CPL_DEBUG', 'OFF')

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


def copy_features(src_layer, dst_layer, fix_geometry, simplify_geometry, batch_size, count_src, count_dst, count_insert, start_index):
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

def append(input_file, output_fusion_table, batch_size):
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
        count_src = src_layer.GetFeatureCount()
        count_dst = dst_layer.GetFeatureCount()

    index = 0
    index_batch = 0
    for feat in src_layer:
        print('index: {0} index_batch: {1}'.format(index, index_batch))

        try:
            geom = shapely.wkt.loads(feat.GetGeometryRef().ExportToWkt())
        except Exception as e:
            print('Error({0}), skipping geometry.'.format(e))
            continue

        #if fix_geometry and not geom.is_valid:
        #    geom = geom.buffer(0.0)

        #if simplify_geometry:
        #    geom = geom.simplify(0.004)

        f = ogr.Feature(dst_layer.GetLayerDefn())

        # print('Adding feature ...')

        # set field values
        for i in range(feat.GetFieldCount()):
            fd = feat.GetFieldDefnRef(i)
            f.SetField(fd.GetName(), feat.GetField(fd.GetName()))
            # print('{0}: {1}'.format(fd.GetName(), feat.GetField(fd.GetName())))

        # set geometry 
        g = ogr.CreateGeometryFromWkt(geom.to_wkt())   
        f.SetGeometry(g)

        if index_batch == 0:
            dst_layer.StartTransaction()

        # create feature
        feature = dst_layer.CreateFeature(f)

        f.Destroy()

        index_batch = index_batch + 1

        if index_batch >= batch_size or index == count_src - 1:
            dst_layer.CommitTransaction()
            count = dst_layer.GetFeatureCount() # update number of inserted features

            index_batch = 0

        index = index + 1


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


    if args.append:
        append(args.input_file, args.output_fusion_table, batch_size)

    # convert(args.input_file, args.output_fusion_table, batch_size, args.add_missing, args.append)
