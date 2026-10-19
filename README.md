# Lyttelton / Whakaraupō

A local 3D landscape prototype with generated ground materials, covering a **10 × 10 km NZTM square** centred on Lyttelton (172.720° E, 43.603° S). Includes the township and port, Whakaraupō / Lyttelton Harbour, surrounding Port Hills and Diamond Harbour.

## Run the prepared world

```sh
cd lyttelton-world
npm install
npm run dev
```

Open the local URL printed by Vite. Prepared world assets are local and excluded from Git; they are already present on the machine where this prototype was generated. Another checkout must prepare them first.

## Prepare or rebuild data

Requires Node.js 20.19+ or 22.12+, Python 3.12+ and `uv` (or an equivalent Python virtual environment).

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.lock
npm run data
npm run validate:data
.venv/bin/python tools/vegetation_coverage.py
```

Preparation reads public LINZ Cloud Optimised GeoTIFFs using HTTP range requests, clips/downsamples only relevant areas, and caches OSM responses. No API key is required. The first preparation downloads many small source windows and can take several minutes. Budget approximately 1–2 GB for the cache and generated data. Interrupted downloads resume from completed cached raster windows.

```sh
npm run data -- --offline   # rebuild from a completed cache, without network access
npm test                   # sampling, coastline and roof-fitting tests
npm run build              # type check and production output
npm run preview            # serve the production output locally
```

The `--stage rasters` option prepares only the cached elevation, surface and imagery mosaics. `--stage features` still validates source selection and uses existing raster mosaics, then rebuilds world features and viewer tiles.

Source metadata, dates, licences, providers, counts and approximation notes are written to `public/world/manifest.json`. A compact record of the delivered dataset and verification is included in `data-provenance.json`. Data caches and generated world assets live entirely inside this folder. Existing repository modules and the native demo are independent.

## Explore

- Drag to orbit, scroll to zoom, and right-drag to pan. Touch uses the usual one-finger orbit and two-finger zoom/pan gestures.
- Choose **Fly**, drag to look, and use **W A S D** to move. **Q / E** move down/up; **Shift** increases speed; scroll adjusts speed. Click the view if keyboard focus has moved elsewhere.
- Use the four place shortcuts or **Reset view**.
- Generated grass, rock, soil and paving are the default ground surfaces. Toggle **Aerial reference** to compare with the photograph. Buildings, roads, vegetation and wireframe remain separate layers.
- Click a building to inspect its height source, roof form and fit error. Open **About this world & sources** for survey links and limitations.
- Phone controls start collapsed to leave the landscape visible.

## What is measured

- **Terrain:** LINZ national LiDAR mosaic, overlaid with Banks Peninsula 2023 and Christchurch 2024–25 DEMs. The national mosaic supplies measured fallback coverage where the selected regional surveys have gaps. The newer survey overlays valid pixels of the older survey. Heights remain NZVD2016 metres without vertical exaggeration.
- **Surface evidence:** 2025 Canterbury rural and Christchurch urban aerial imagery supplies colour evidence, with DEM/DSM height differences and OSM geometry constraints. It is classified at 2 m into grass, rock, soil, paving, canopy and water. Aerial RGB is not rendered on generated ground.
- **Building positions:** OSM footprints, including multipolygons and courtyards.
- **Building heights and roofs:** a 2 m resampling of the LINZ DSM is sampled inside each footprint. Sufficient valid samples supply measured heights. Flat and two-plane gable candidates are compared; a gable is retained only when it meaningfully reduces fit error. This is a conservative prototype, not a validated building survey or full roof reconstruction system.
- **Vegetation:** LiDAR height differences, colour evidence and mapped woodland identify raised vegetation, including shaded stands and low scrub. Canopy peaks seed the placement; overlapping crown/low-scrub clusters fill the measured footprint between peaks. These are rendering instances, not a count of real trees. Roots remain outside building footprints and mapped roads; crowns can overhang them.
- **Roof colour:** robust median aerial colour samples inside each footprint; colours are evidence-informed, not verified facade materials.
- **Road routes and coastline:** OSM. Coastline direction and polygon topology determine the harbour surface and islands.

## What is approximate

The surface classifier is an explicit RGB/height/rule baseline, not a trained AI semantic model. Roof/building masks prevent photographed rooftops becoming ground textures; mapped roads override ambiguous image colour. Dark shadows, survey-date differences and similar-looking materials can still cause misclassification. Generated materials are evaluated in world metres with multiple scales of colour and bump detail, so they do not stretch with tile size or level of detail.

Walls are untextured, with no observed doors, windows, signs, balconies or facade materials. Complex and unsupported roofs use a flat approximation. DSM samples can include vegetation and can disagree with OSM footprints because surveys have different dates. Roof error describes fit to those samples, not independently verified real-world accuracy.

Buildings without sufficient surface evidence use an OSM height or storey count, then a labelled 6 m default. Road widths use an OSM `width` tag, else an estimate from separately mapped sidewalks (twice their median offset from the centreline, less the footpath and kerb margin), else a class default. Lane markings and painted crossings follow OSM class, width and crossing tags; they are conventions rather than surveyed paint. Bridges interpolate endpoint heights and are not engineered structures; tunnels are omitted. Roads do not modify the terrain. Vegetation positions combine detected canopy peaks and footprint coverage fill. Heights follow LiDAR; broad crown widths, low-scrub cluster extents, species and geometry remain approximate. Mapped woodland can preserve vegetation whose aerial colour is shaded or desaturated. Water is a flat surface at 0 m NZVD2016, not a tide or bathymetry model.

Terrain vertices are 10 m apart at the finest display level. Near/far tiles use 10/20/40 m grids, with boundary skirts to cover LOD seams. This is intended for landscape exploration; detailed ground-level pavement, retaining walls and collision are future work. The world has a finite rectangular boundary.

The pipeline never invents missing land elevation: affected samples remain missing and corresponding terrain triangles are omitted. Source coverage issues are reported in the manifest and source panel.

## Data and rendering interfaces

`world.config.json` records the region, source collections and generation seed. This initial pipeline deliberately supports **this fixed 10 km BX24 region**; it checks the map-sheet extent before using tile-name selection. The pipeline rejects changed raster configuration when existing cache products would become stale. Move `.cache` aside before changing the region, resolution or source collections. Processing-algorithm changes also require rebuilding affected cached products.

`npm run surfaces` rebuilds the surface evidence, canopy placements and roof colours from the existing cache without downloading data or rebuilding roof geometry. Full `npm run data` also runs this stage.

`public/world/manifest.json` is the version-1 entry point. It references 100 one-kilometre tiles, a global elevation grid and `features.json`. Tile height buffers are little-endian float32, 101 × 101, row-major from north to south. Geometry uses local east/north metres; Three.js maps east to X, elevation to Y, and south to Z. Aerial reference tile images are north-up WebP. Generated terrain reads 502 × 502 RGB control maps: red is grass, green is rock, blue is soil, and paving is the remaining weight. Each 500 × 500 interior has a one-pixel neighbour gutter. These maps contain class weights only. A 1000 × 1000 overview supports the coarse terrain base. A compact 10 m class-index grid is included for subsequent placement tools. Building roof parameters and their evidence source remain inspectable in feature data.

A complete coarse terrain base remains present while detailed tiles load nearest-first with bounded concurrency. Distant terrain resources are disposed; geometry changes level of detail with camera distance. Buildings are batched. Vegetation is instanced in one-kilometre chunks: nearby crowns retain fuller geometry and trunks; distant chunks use simpler crowns sharing the instance buffers. The prepared viewer fetches only local files; linked source sites are opened only when selected.

## Browser checks

With the dev server running:

```sh
npx playwright test
```

The supplied configuration uses installed Google Chrome on macOS. Set `PLAYWRIGHT_CHROME` to a compatible Chromium executable on another platform. Checks cover loading real data, layer controls, fly movement, building selection, tile disposal, phone layout and a missing-data error. Captures are written under `.impeccable/review/`.

## Attribution

Elevation and aerial imagery: **Toitū Te Whenua Land Information New Zealand and the survey providers named in the world manifest**, under the collection licences (CC BY 4.0). See [LINZ data licensing and attribution](https://www.linz.govt.nz/products-services/data/licensing-and-using-data).

Map features: **© OpenStreetMap contributors**, [ODbL](https://www.openstreetmap.org/copyright). Source links are visible in the viewer. Preserve data licences and provider attribution when distributing prepared assets or derivative databases.

The vegetation coverage check rasterizes conservative projected crown footprints against the detected canopy mask. It caught the original sparse-peak rendering (about 10% coverage) and now checks for at least 80%. This measures coverage of the inferred mask, not independent identification accuracy or surveyed individual trees.

### Repeatable aerial comparison

Run `npm run compare` while the dev server is running. It captures the harbour, town, hills and Diamond Harbour with identical cameras in generated and aerial modes, saving a side-by-side report at `reports/comparison/index.html`. The aerial capture hides reconstructed buildings, roads and vegetation, so the photograph remains visible for comparison. `COMPARE_OUT=reports/comparison/before npm run compare` keeps a named baseline.

The landscape controls encode canopy occupancy, a growing-grass category, DEM sky openness and fixed-sun visibility. Low scrub is clipped to detected occupancy, while taller crowns may overhang. Ground below foliage uses a darker forest-floor material. Controls contain no aerial RGB; grass condition is a categorical estimate and can misclassify shaded/dry ground.

`npm run hillshade` caches the published [LINZ 1m DEM hillshade](https://nz-elevation.s3-ap-southeast-2.amazonaws.com/new-zealand/new-zealand/dem-hillshade_1m/2193/collection.json) for this area. Then run `npm run surfaces` to incorporate its fine relief into generated terrain lighting. A local ratio removes broad fixed-direction shading before use, reducing double lighting with the 3D sun. The source is sampled at 2 m and rendered as 5 m lighting detail; this does not increase the 10 m terrain mesh resolution. Without the optional cache, the pipeline writes neutral detail. DEM horizon visibility uses the same sun direction as the viewer and is independent of the aerial photograph.

### Native plant models

The first installed species is **tī kōuka / cabbage tree (Cordyline australis)**, an actual textured PlantCatalog model downloaded through Sketchfab under CC BY 4.0. Its original GLB and attribution are in `public/plants/cc-by/` and `public/plants/ATTRIBUTION.md`. Use **Native plants** in the viewer to inspect it.

Detailed models render within 180m of the camera, with a global limit of 48 instances. They replace selected compatible proxy crowns/trunks; those proxies return when leaving the area. The current cabbage-tree model is restricted to 3.5–9m measured vegetation and a deterministic 2.5% subset. This is illustrative species assignment, not a claim that those locations contain surveyed cabbage trees. Shrubs and other tree species still use approximate generated geometry. Sources show model author and licence.

`public/plants/catalog.json` registers local, self-contained GLBs. Add verified CC BY 4.0 or CC0 assets with:

```sh
npm run plant:install -- \
  --file /path/to/plant.glb --id species-name \
  --species 'Scientific name / common name' --author 'Creator' \
  --license CC-BY-4.0 --source https://example.com/model-page \
  --kind shrub --min-height 0.8 --max-height 3 --density 0.025
```

The installer rejects external resources, unsupported compressed assets, animation, more than 16 mesh parts, more than 250,000 triangles, or files over 40MB. Runtime normalizes origins/heights and instances static geometry. Retain credits alongside distributed files. Commercial assets must be separately licensed for the intended delivery and are not included by this free-asset importer.


### Close-range foliage and scanned ground

Nearby crowns and scrub proxies yield to representative trees and bushes generated in the browser with [EZ-Tree](https://github.com/dgreenheck/ez-tree) (MIT). Ten variants (broadleaf, slender, tall broadleaf, conifer and bush forms) are built once from its presets with denser foliage and green leaf textures, normalized to unit height and instanced. They are illustrative forms, **not identified NZ species**. The named native model remains the PlantCatalog cabbage tree.

Trees scale to LiDAR height and follow the measured crown width only loosely, keeping natural proportions. A low-scrub instance is a measured cluster, not a single plant, so it is filled with several bushes rather than one stretched model. Leaves are tinted toward the aerial-sampled crown colour. The detailed budget is 2,000 instances and 6 million submitted triangles inside a widened view cone; trees render within 150–170 m and bushes within 75 m. Named species stay limited to 48 instances.

Mid-range and distant vegetation keeps instanced proxy crowns, now with smooth, lumpy geometry (80, 20 and 8 triangles by distance) and a foliage shader: world-space leaf clumps, darker undersides and bush-scale mottling on low scrub. Shaded aerial samples, which read blue-black, are lifted toward sunlit foliage colour.

The generated ground now blends local CC0 grass and forest-floor scans at their recorded physical scale. Colour, OpenGL normal and roughness maps add close detail, fading to existing ground colours between 65–220m. Canopy occupancy selects forest-floor blending; soil and paving retain their geographic masks. The forest-floor albedo is toned down and desaturated in the shader; the source maps are unmodified. Materials are representative surface samples, not photographs of the actual Lyttelton ground. Geographic aerial imagery remains off by default.

### Roads and footpaths

Roads, footpaths and tracks are continuous ribbons with mitred joins. Each cross-section drapes its edges and centre onto the displayed terrain; bridges keep their interpolated deck. Sealed roads use the CC0 Poly Haven *Tarred Gravel* scan (close to NZ chipseal), footpaths and sealed paths *Asphalt Floor*, and tracks or paths tagged gravel/ground/grass *Gravel Road*. Scan colours are rescaled in the shader to the median aerial colour sampled along mapped centrelines. Two-lane streets get dashed centre lines; main roads also get edge lines; markings stop short of junctions. Marked OSM crossings get zebra bars or signal lines. Higher road classes draw over lower ones where they overlap.

Rebuild downloaded surface scans with `npm run assets:fetch`. This uses the Poly Haven public API during preparation only; the viewer loads all maps locally. Procedural foliage needs no download. Source metadata and SHA-256 checksums are saved in `public/materials/sources.json`. Surface credits are in `public/materials/ATTRIBUTION.md`, and foliage credits are in `public/plants/ATTRIBUTION.md`.
