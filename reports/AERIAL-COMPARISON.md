# Aerial / reconstructed world comparison

Matched cameras cover the harbour overview, Lyttelton township, Port Hills and Diamond Harbour. `npm run compare` saves an HTML report and image pairs. Aerial captures hide generated buildings, roads and vegetation so these cannot obscure evidence. Water retains the same measured coastline geometry in both views. Comparison images are local generated artifacts and are ignored by Git.

This pass keeps baseline pairs in `reports/comparison/before/` and updated pairs in `reports/comparison/after/`.

## Changes from comparison

- Grass previously looked uniformly yellow across dry hills and greener areas. A categorical growing-grass control now varies the generated material, with a more neutral dry-grass palette.
- Low, broad scrub crowns extended past measured foliage and read as scattered polygons on bare slopes. Low scrub now clips against the vegetation occupancy control; taller crowns retain overhang.
- Ground below canopy used the open-grass material. It now transitions to darker forest floor.
- Gullies lacked terrain enclosure and fine relief. DEM horizon tests provide sky openness and fixed-sun visibility. The published LINZ 1m DEM hillshade contributes local fine-relief lighting after removing broad fixed-direction illumination.

## Hillshade source and limits

[LINZ elevation repository](https://github.com/linz/elevation#hillshade) describes the available DEM/DSM products. This pass caches the [New Zealand 1m DEM Hillshade collection](https://nz-elevation.s3-ap-southeast-2.amazonaws.com/new-zealand/new-zealand/dem-hillshade_1m/2193/collection.json), BX24, under CC BY 4.0. Its metadata specifies 315° azimuth and 45° elevation. The viewer keeps terrain colour procedural, samples hillshade at 2m, normalizes against a 12m-radius blurred version, and renders the residual at 5m. It does not paste the full fixed-light hillshade over the landscape or increase geometric detail.

Grass condition and canopy occupancy remain heuristic categories derived from imagery, elevation and OSM constraints. They do not store photographic RGB. Terrain sky/sun controls derive only from DEM. The existing 93.19% conservative crown-footprint measure describes reach across the inferred vegetation mask before the new low-scrub fragment constraint; it is not an independent accuracy measure or a whole-world similarity score.

## Remaining gaps visible in comparison

The result is still an approximate reconstruction. Terrain meshes range from 10m nearby to 40m distant. Small cliffs, retaining walls and roadside cuts need finer geometry. Many roofs remain flat approximations, facades lack observed detail, and port cranes, rail infrastructure, cargo stacks and small street objects are absent. Grass texture and plant species are procedural. Source acquisition dates differ. Better lighting cannot resolve those missing objects or establish their dimensions.

## Validation

21 Python tests, 5 browser tests and production build pass. Prepared-data validation checks 180 shared terrain edges, matching surface gutters, object exclusions and landscape control dimensions. Browser checks report zero external requests and no page/console errors. The browser tests also cover layer toggles, navigation, building inspection, mobile controls, missing data and delayed scene initialization.
