"""See https://github.com/casperdcl/world-map for details"""
# %% Load data
from base64 import b64encode
from math import pi
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import svgwrite
import svgwrite.container
from matplotlib import colormaps
from PIL import Image
from shapely import box

__author__ = "Casper da Costa-Luis (https://github.com/casperdcl)"
__license__ = "MPL-2.0"
__version__ = "0.0.0"

# Eckert II, ESRI:53014, https://epsg.io/53014
to_crs = "+proj=eck2 +lon_0=0 +x_0=0 +y_0=0 +R=6371000 +units=m +no_defs +type=crs"
aspect = pi / 2
# WGS84, EPSG:4326, https://epsg.io/4326
# to_crs = "WGS84"

# https://www.naturalearthdata.com/downloads/50m-cultural-vectors/
# https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip
gdf = gpd.read_file("ne_50m_admin_0_countries.shp")
orig_crs = gdf.crs
gdf = gdf.to_crs(to_crs)
# https://www.naturalearthdata.com/downloads/50m-physical-vectors/
rivers = gpd.read_file("ne_50m_rivers_lake_centerlines_scale_rank.shp").to_crs(to_crs)
lakes = gpd.read_file("ne_50m_lakes.shp").to_crs(to_crs)
glaciers = gpd.read_file("ne_50m_glaciated_areas.shp").to_crs(to_crs)
geolines = gpd.read_file("ne_50m_geographic_lines.shp").to_crs(to_crs)
# graticules
grid = [box(lon, lat, lon + 10, lat + 10) for lat in range(-90, 90, 10) for lon in range(-180, 180, 10)]
grid = gpd.GeoSeries(grid, crs=orig_crs).to_crs(gdf.crs)

# https://www.naturalearthdata.com/downloads/50m-raster-data/50m-natural-earth-2/
if not (fname := Path("ne_50m_relief.jpg")).is_file():
    # https://rasterio.readthedocs.io/en/latest/topics/reproject.html
    import rasterio
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    with rasterio.open("NE2_50M_SR_W/NE2_50M_SR_W.tif", crs="WGS84") as src:
        left, bottom, right, top = src.bounds
        transform, width, height = calculate_default_transform(
            src.crs, to_crs, src.width, src.height, left, bottom, right, top,
            dst_width=10_000, dst_height=src.height * 10_000 // src.width)
        arr = np.zeros((src.count, height, width), dtype=np.uint8)
        for i in range(src.count):
            reproject(source=rasterio.band(src, i + 1), destination=arr[i],
                      src_transform=src.transform, src_crs=src.crs, dst_transform=transform, dst_crs=to_crs,
                      resampling=Resampling.bilinear)

    Image.fromarray(arr.transpose(1, 2, 0)).save(fname, quality=100)

# %% Build graph of countries & colour them

water = '#6baed6'
# colour based on four-colour theorem

G = nx.Graph()
for iii, row in gdf.iterrows():
    G.add_node(iii)
    for j, _neighbour in gdf[gdf.geometry.touches(row.geometry)].iterrows():
        G.add_edge(iii, j)
colors = nx.coloring.greedy_color(G, strategy="smallest_last")


def rgb2hex(rgb):
    return '#%02x%02x%02x' % tuple(int(v * 255) for v in rgb)


color_map = list(map(rgb2hex, np.asarray(colormaps.get('Set2').colors)[[4, 5, 6, 3, 1]]))

# red, blue, green, _, _, yellow, _, _, _ = map(rgb2hex, colormaps.get('Pastel1').colors)
# black = rgb2hex(colormaps.get('Pastel2').colors[-1])
red, blue, green, yellow, black = 'red', 'blue', 'green', 'yellow', 'black'
olympic_colors = {
    'Africa': green,
    'Antarctica': 'white',
    'Asia': red,
    'Europe': black,
    'North America': blue,
    'Oceania': green,
    'Seven seas (open ocean)': water,
    'South America': yellow}

# %% Create SVG, inspired by http://kuanbutts.com/2018/09/06/geodataframe-to-svg-2

'''
# matplotlib version
import matplotlib.pyplot as plt
ax = gdf.plot(
    color=gdf.index.map(lambda x: color_map[colors[x]]),
    edgecolor="black", linewidth=0.5,
    figsize=(aspect * (size := 3 * 12), size), zorder=1)
ax.set_axis_off()
ax.set_xlim(-(x:=18.5e6), x)
ax.set_ylim(-(y:=9.3e6), y)
ax.set_facecolor(water)

# add graticules & water
grid.plot(ax=ax, color=water, zorder=0)
grid.plot(ax=ax, edgecolor='black', alpha=0.1, linewidth=0.5, zorder=2)

plt.savefig("world-map.jpg", dpi=90, bbox_inches='tight', pad_inches=0, facecolor=water)
'''

scale = 0.1 if to_crs == "WGS84" else 1e-6
viewbox = grid.total_bounds * scale
viewbox[2:] -= viewbox[:2]
dwg = svgwrite.Drawing("world-map.svg", height='100%', width='100%', viewBox=' '.join(map(str, viewbox)))
dwg.fill(color=water)
dwg.stroke(color=water, width=0.01)


g = svgwrite.container.Group(id='relief')
dwg.add(dwg.image(href=f"data:image/jpeg;base64,{b64encode(Path(fname).read_bytes()).decode()}",
                  height='100%', width='100%', x=viewbox[0], y=viewbox[1]))

'''
# solid sea version
g = svgwrite.container.Group(id='sea')
for row in grid:
    g.add(dwg.polygon(points=np.asanyarray(row.exterior.coords.xy).T[:-1] * [scale, -scale]))
dwg.add(g)
'''

g = svgwrite.container.Group(id='countries', opacity=0.15)
for continent, fill in olympic_colors.items():
    gcont = svgwrite.container.Group(id=continent.replace(' ', '_').replace('(', '').replace(')', ''), fill=fill)
    for row in gdf[gdf['CONTINENT'] == continent].itertuples():
        # fill = 'white' if row['NAME'] == "Antarctica" else rgba_to_hex(color_map[colors[i]])
        gc = svgwrite.container.Group(id=row.NAME.replace(' ', '_'))
        for poly in getattr(row.geometry, 'geoms', [row.geometry]):
            gc.add(dwg.polygon(points=np.asanyarray(poly.exterior.coords.xy).T[:-1] * [scale, -scale], fill=fill))
        gcont.add(gc)
    g.add(gcont)
dwg.add(g)

g = svgwrite.container.Group(id='rivers')
for row in rivers.itertuples():
    for poly in getattr(row.geometry, 'geoms', [row.geometry]):
        g.add(dwg.polyline(points=np.asanyarray(poly.coords.xy).T * [scale, -scale],
                           fill='none'))
dwg.add(g)

g = svgwrite.container.Group(id='lakes')
for row in lakes.itertuples():
    for poly in getattr(row.geometry, 'geoms', [row.geometry]):
        g.add(dwg.polygon(points=np.asanyarray(poly.exterior.coords.xy).T[:-1] * [scale, -scale],
                          stroke='none'))
dwg.add(g)

g = svgwrite.container.Group(id='glaciers')
for row in glaciers.itertuples():
    for poly in getattr(row.geometry, 'geoms', [row.geometry]):
        g.add(dwg.polygon(points=np.asanyarray(poly.exterior.coords.xy).T[:-1] * [scale, -scale],
                          stroke='none', fill='white'))
dwg.add(g)

g = svgwrite.container.Group(id='graticules')
for row in grid:
    g.add(dwg.polygon(points=np.asanyarray(row.exterior.coords.xy).T[:-1] * [scale, -scale],
                      fill='none', stroke='black', stroke_opacity=0.1))
dwg.add(g)

g = svgwrite.container.Group(id='geographic_lines')
for row in geolines.itertuples():
    gc = svgwrite.container.Group(id=row.name.replace(' ', '_'))
    for poly in getattr(row.geometry, 'geoms', [row.geometry]):
        gc.add(dwg.polyline(points=np.asanyarray(poly.coords.xy).T * [scale, -scale],
                            fill='none', stroke='black', stroke_opacity=0.2, stroke_dasharray='0.1', stroke_width=0.03))
    g.add(gc)
dwg.add(g)

g = svgwrite.container.Group(id='borders')
for _, row in gdf.iterrows():
    for poly in getattr(row.geometry, 'geoms', [row.geometry]):
        g.add(dwg.polygon(points=np.asanyarray(poly.exterior.coords.xy).T[:-1] * [scale, -scale],
                          fill='none', stroke='black'))
dwg.add(g)

dwg.save()
