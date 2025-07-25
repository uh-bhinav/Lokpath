import exifread

def extract_gps(image_path):
    with open(image_path, 'rb') as f:
        tags = exifread.process_file(f)
        if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
            lat_values = tags['GPS GPSLatitude'].values
            lon_values = tags['GPS GPSLongitude'].values
            lat_ref = tags['GPS GPSLatitudeRef'].values
            lon_ref = tags['GPS GPSLongitudeRef'].values

            def to_deg(value):
                return float(value[0].num) / value[0].den + \
                       float(value[1].num) / value[1].den / 60 + \
                       float(value[2].num) / value[2].den / 3600

            lat = to_deg(lat_values)
            lon = to_deg(lon_values)

            if lat_ref != 'N':
                lat = -lat
            if lon_ref != 'E':
                lon = -lon

            return {'latitude': lat, 'longitude': lon}
    return None
