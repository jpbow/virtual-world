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

The surface classifier is an explicit RGB/height/rule baseline, not a trained AI semantic model. Roof/building masks prevent photographed rooftops becoming ground textures; mapped roads override ambiguous image colour. Paving needs neutral grey imagery that its neighbours support. Yellow-green lawns and gardens near buildings stay grass, and so do isolated grey pixels such as paths and sheds. Cast shadows carry no surface evidence, so each one takes the class of the lit ground around it. Inside extensive hardstand, tinted gravel, log stacks and stains count as paving. Ground under roofs takes the surrounding class: gardens around houses, paving around port sheds. Grass in town is shaded as growing lawn when shrubs or trees make up at least 40% of its 14 m surroundings; this is inferred from neighbourhood, not observed per lawn. OSM in this area maps no car parks or residential land use, so car parks, port hardstand and unmapped driveways are recognised from colour alone. Narrow or tinted driveways, patios and gravel paths can be read as grass, and grey dead lawns as paving. Survey-date differences and similar-looking materials can still cause misclassification. Generated materials are evaluated in world metres with multiple scales of colour and bump detail, so they do not stretch with tile size or level of detail.

Walls are untextured, with no observed doors, windows, signs, balconies or facade materials. Complex and unsupported roofs use a flat approximation. DSM samples can include vegetation and can disagree with OSM footprints because surveys have different dates. Roof error describes fit to those samples, not independently verified real-world accuracy.

Buildings without sufficient surface evidence use an OSM height or storey count, then a labelled 6 m default. Road widths use an OSM `width` tag, else an estimate from separately mapped sidewalks (twice their median offset from the centreline, less the footpath and kerb margin), else a class default. Lane markings and painted crossings follow OSM class, width and crossing tags; they are conventions rather than surveyed paint. Bridges interpolate endpoint heights and are not engineered structures; tunnels are omitted. Roads do not modify the terrain; road ribbons drape onto the exact displayed terrain triangles every 2.5 m. Vegetation positions combine detected canopy peaks and footprint coverage fill. Heights follow LiDAR; broad crown widths, low-scrub cluster extents, species and geometry remain approximate. Mapped woodland can preserve vegetation whose aerial colour is shaded or desaturated. Water is a flat surface at 0 m NZVD2016, not a tide or bathymetry model.

Terrain vertices are 10 m apart at the finest display level. Near/far tiles use 10/20/40 m grids, with boundary skirts to cover LOD seams. This is intended for landscape exploration; detailed ground-level pavement, retaining walls and collision are future work. The world has a finite rectangular boundary.

The pipeline never invents missing land elevation: affected samples remain missing and corresponding terrain triangles are omitted. Source coverage issues are reported in the manifest and source panel.

## Data and rendering interfaces

`world.config.json` records the region, source collections and generation seed. This initial pipeline deliberately supports **this fixed 10 km BX24 region**; it checks the map-sheet extent before using tile-name selection. The pipeline rejects changed raster configuration when existing cache products would become stale. Move `.cache` aside before changing the region, resolution or source collections. Processing-algorithm changes also require rebuilding affected cached products.

`npm run surfaces` rebuilds the surface evidence, canopy placements and roof colours from the existing cache without downloading data or rebuilding roof geometry. Full `npm run data` also runs this stage.

`public/world/manifest.json` is the version-1 entry point. It references 100 one-kilometre tiles, a global elevation grid and `features.json`. Tile height buffers are little-endian float32, 101 × 101, row-major from north to south. Geometry uses local east/north metres; Three.js maps east to X, elevation to Y, and south to Z. Aerial reference tile images are north-up WebP. Generated terrain reads 502 × 502 RGB control maps: red is grass, green is rock, blue is soil, and paving is the remaining weight. Each 500 × 500 interior has a one-pixel neighbour gutter. These maps contain class weights only. A 1000 × 1000 overview supports the coarse terrain base. A compact 10 m class-index grid is included for subsequent placement tools. Building roof parameters and their evidence source remain inspectable in feature data.

A complete coarse terrain base remains present while detailed tiles load nearest-first with bounded concurrency. Distant terrain resources are disposed; geometry changes level of detail with camera distance. Buildings are batched. Vegetation is instanced in one-kilometre chunks: nearby crowns retain fuller geometry and trunks; distant chunks use simpler crowns sharing the instance buffers. The prepared viewer fetches only local files, except the optional live aerial reference below; linked source sites are opened only when selected.

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

### Live high-resolution aerial reference

**Aerial reference** mode can stream [LINZ Basemaps](https://basemaps.linz.govt.nz/) aerial tiles, up to the native 7.5 cm imagery, instead of the local 1 m tiles. Put a Basemaps API key in `.env.local` (git-ignored; see `.env.example`), then restart `npm run dev`:

```sh
VITE_LINZ_BASEMAPS_KEY=your-key
```

A standard key is free from basemaps.linz.govt.nz without registration, lasts 90 days and is rate limited (1,000 requests a minute); LINZ can issue non-expiring developer keys. Tiles use the NZTM2000Quad grid, which shares the world's EPSG:2193 coordinates. A quadtree refines tiles inside the view (plus a margin) until their pixels are about as fine as screen pixels, down to zoom 19 (~7.5 cm). A fresh close-up view requests roughly 250–500 small tiles and settles in about 5 s; the browser caches them, and failed tiles retry after 15 s. A tile is replaced by its four children only once all of them have loaded, and the patches replace the local terrain once the coarse tiles cover the world. Without a key or network, the local 1 m tiles show. The key is embedded in the client bundle, so treat a production build as carrying it. Imagery: LINZ Basemaps, CC BY 4.0.

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

The generated ground now blends local CC0 grass and forest-floor scans at their recorded physical scale. Dry pasture uses Poly Haven *Grass Ground*; grass within 30 m of a building, including under garden trees, is treated as mown lawn and uses ambientCG *Grass004* with *Grass001* colour variation, sampled at two rotated scales to hide repetition, unless the aerial pixel is clearly brown. Colour, OpenGL normal and roughness maps add close detail, fading to existing ground colours between 65–220m. Canopy occupancy selects forest-floor blending; soil and paving retain their geographic masks. The forest-floor albedo is toned down and desaturated in the shader; the source maps are unmodified. Materials are representative surface samples, not photographs of the actual Lyttelton ground. Geographic aerial imagery remains off by default.

### Roads and footpaths

Roads, footpaths and tracks are continuous ribbons with mitred joins. Each cross-section drapes its edges and centre onto the displayed terrain; bridges keep their interpolated deck. Sealed roads use the CC0 Poly Haven *Tarred Gravel* scan (close to NZ chipseal), footpaths and sealed paths *Asphalt Floor*, and tracks or paths tagged gravel/ground/grass *Gravel Road*. Scan colours are rescaled in the shader to the median aerial colour sampled along mapped centrelines. Two-lane streets get dashed centre lines; main roads also get edge lines; markings stop short of junctions. Marked OSM crossings get zebra bars or signal lines. Higher road classes draw over lower ones where they overlap.

Rebuild downloaded surface scans with `npm run assets:fetch`. This uses the Poly Haven public API during preparation only; the viewer loads all maps locally. Procedural foliage needs no download. Source metadata and SHA-256 checksums are saved in `public/materials/sources.json`. Surface credits are in `public/materials/ATTRIBUTION.md`, and foliage credits are in `public/plants/ATTRIBUTION.md`.

### Detailed London Street buildings (Blender)

`npm run buildings -- --name london` replaces the generic extruded boxes for 42 buildings along London Street, from the west end of the residential stretch to Canterbury Street, with Blender models: shopfronts, house windows and doors, garage and roller doors, false fronts and shaped parapets, verandahs with posts, signs and painted lettering, cladding (weatherboard, board and batten, corrugated iron, render, tile or brick) and hipped, gabled, twin-gabled or flat roofs. Houses and service buildings sit at their own ground level, so those above retaining walls or below the street keep their doors and windows where the photos show them.

Each model combines three sources:
- **Footprint and frontage:** the OSM footprint; the facade is the footprint edge facing London Street.
- **Measured from LiDAR** (LINZ Christchurch 2024-25 1 m DEM and DSM, read once from the public COGs and cached in `.cache/`): footpath level, roof kind, eave height and pitch (least-squares fits of flat, shed, gable, gable-end and hip roofs, trimmed of vents and trees), parapet height, verandah depth and height over the footpath, and where a hip or gable covers only the front of a deep footprint, the lower rear section. On two-storey buildings the facade is registered to the LiDAR roof edge: several OSM footprints sit 1–2 m behind or in front of the real facade.
- **Observed in street photos** and written into `buildings/london.json` with the photo each came from: storeys, cladding and colours, parapet shape, window count and type, shopfront layout, verandah type and post colour, and sign text. Google Street View (April 2025) was viewed for reference only; nothing from it is copied into the models. Wikimedia Commons photos are credited per building.

Window sizes, glazing bars and door positions are typical rather than measured, and colours are estimated by eye. The library's pitched black roofs are simplified to its measured ~5 m roof, tower and gabled wing. The OSM polygon tagged Everest is the restaurant's covered seating; the LiDAR and photos put the restaurant in the footprint beside it, so the spec swaps them. OSM maps the whole fire station site as a building; the model of the station building replaces it. Dormers are not modelled.

Outputs: `buildings/london.blend` (one collection per building, textures packed, editable) and `public/buildings/london.glb`. `--measure` prints the measurements without building; `--export` re-exports an edited `.blend` without rebuilding it. In the viewer, the models replace their footprints (and any listed in `replaces`) and stay selectable: the inspector shows the model and its photo evidence.

### The rest of Lyttelton (typed buildings)

`npm run buildings -- --name lyttelton` models every other building in the township and port (`buildings/lyttelton.json`: about 1,850, from Naval Point to Cashin Quay) the same way as London Street, except for the facade notes, which nobody has written for these buildings. Footprints are OSM. LiDAR measures each building's frontage level, its own ground level, facade registration, roof form and pitch (L-shaped houses get a separate roof on each wing), eave height and storeys, and the roof colour comes from the aerial. The facade comes from the building's type (`tools/building_typology.py`):

- **Type** from OSM tags where present (`building=*`, or a shop, office, café, etc. on the building), else from the footprint: round footprints are tanks (Naval Point), under 28 m² outbuildings, large or port-side ones industrial, the rest houses.
- **Facade by type:** weatherboard houses with ground-floor windows and a front door (and upper windows on two-storey houses), sheds and garages with a garage door where they face a road, industrial sheds in corrugated iron with roller doors, shops with shopfronts (and a verandah only where the LiDAR shows one), civic buildings with paired windows, white tanks. Window and door counts follow the measured frontage.
- **Colours** are drawn per building from a palette of colours common in Lyttelton. They are illustrative, not observed; the inspector says so for every typed building.

Typed buildings face the nearest road or path (else their longest edge). To give one an observed facade, add an entry to `buildings[]` in `buildings/lyttelton.json` with the same fields as `london.json`; it then replaces the typed version.

The area builds as merged meshes on a 400 m grid (`public/buildings/lyttelton.glb`, about 40 MB): each chunk shares one material per surface (weatherboard, corrugated iron, render, glass…) and carries every building's colours as vertex colours, about a dozen materials and 250 draw calls for the whole town. A per-vertex `_BUILDING` attribute keeps buildings selectable. Typed windows are lighter than London Street's (glass, sill and rail, no architraves). The few buildings the measurement cannot handle (degenerate footprints) keep their generic extrusion.

### London Street kerbs and footpaths

`npm run street -- --name london` replaces the flat OSM road ribbon on London Street, between its two junctions, with a street corridor built in Blender: traffic lanes, parking lanes, a 0.3 m concrete gutter, a 150 mm kerb (lowered to a 20 mm ramp at the zebra crossings), the kerb top and paver footpaths up to the building line. Surfaces are cropped from the city kit's atlas (asphalt, concrete, pavers; the pavers greyed to match the London Street photos on Wikimedia Commons).

The kerb lines are measured, not assumed:
- **Parking runs** from the street inventory: cars stand against the kerb, so the kerb is a run's car-centre offset plus half the car's depth across the street at its parking angle, plus a 0.2–0.35 m gap. On London Street that puts the south kerb about 8.4 m from the centreline (angle parking) and the north kerb about 5.5 m (parallel parking); the 1 m LiDAR's gutter and slope break agree. The aerial's own asphalt edge does not: verandahs hide the north footpath and the south side's grey pavers read as asphalt.
- **Zebra crossings** run kerb to kerb, so their bars set the kerbs at the crossings, which sit on build-outs; between spans of evidence the kerb is interpolated.
- **Footpaths** reach the LiDAR-registered facade lines of the modelled buildings, else OSM footprints, else 3 m.

The corridor is laid out every 0.95 m in local metres with z the height above the ground (`streets/london.blend`, `public/streets/london.glb`). The viewer drapes it 6 cm above the terrain, over the road ribbon it covers and under the inventory's measured paint (bay lines, zebras, limit lines), which stays on top. At both junctions (Canterbury Street, and Oxford Street with Sumner Road) the kerbs turn the corner: London Street's carriageway at its end kerbs and each cross-street arm at kerbs set by its own zebra crossing (Oxford Street 6.5 and 4.9 m either side of the centreline, Canterbury Street 4.3 and 4.4 m) are merged, their inside corners rounded to a 5 m kerb radius, and a 3 m footpath wraps around them into the cross street, clear of buildings. Only the corners on London Street's side are built. Street furniture stands on the corridor's surface (footpath or kerb) where there is one. It is part of the *Roads & paths* layer.

### Street furniture kit

`npm run furniture -- --name london` places a reusable street-furniture kit wherever records show an item. The kit is built in Blender by `tools/blender_street_kit.py` (`street-kit/street-kit.blend`, exported to `public/street-kit/street-kit.glb`): ornamental and park lamps, a London Street pedestal litter bin with its compass emblem, a Big Belly compactor, benches with and without backs, a picnic table, bollard, bike hoops, drinking fountain, NZ Post and DX Mail boxes, a payphone, a bus stop, and stop, give way, parking (P5–P120 and a plain P) and no-stopping signs. Styles follow London Street photos; sizes are typical. Each prefab stands on its origin facing +Z in the GLB, so the same model is reused at every placement (one instanced mesh per part).

Placements (`public/street-kit/<name>.json`) come from:
- **OpenStreetMap** (ODbL) nodes: benches (their `direction` sets which way they face), waste baskets, post boxes, payphones, drinking water, bicycle parking, picnic tables, bollards, flagpoles, street lamps (`support=ornamental` picks the heritage lamp), bus stops and stop signs. A stop sign stands at the left kerb of its approach, facing oncoming traffic.
- **Christchurch City Council park asset registers** (CC BY 4.0): seats, bins (`Style` picks the prefab), bollards and light poles, mostly in Albion Square and the reserves.
- **Mapillary** map features (CC BY-SA 4.0): bins, benches, bike racks, mailboxes, street lights and stop, give way, parking and no-parking signs detected in street-level photos. Set a free access token as `MAPILLARY_TOKEN` in `.env.local`; without one this source is skipped. Detections in the carriageway move to the kerb, and signs face their `aligned_direction`. Mapillary's positions are triangulated, so a Mapillary item within 4 m of the same kind from OSM or the council counts as a duplicate. Coverage of London Street is thin: 61 photos from December 2018, which give one bin (on Canterbury Street) beyond what OSM already has, and no signs.
- The street inventory keeps its own street lights; evidence within 6 m of one is not placed again. Items of the same kind within 2.5 m in two sources are one item.

Anything without a recorded direction faces the nearest road. Christchurch's road signs and street lights are in its RAMM asset database, which is not published, and Mapillary has no sign detections here yet, so parking signs are in the kit but not placed; new Mapillary captures will be picked up on the next run (delete `.cache/street-furniture-<name>-mapillary.json` to refetch). Street View imagery is not used for placements: Google's terms do not allow deriving map data from it.

`--kit` rebuilds the kit `.blend` from the script; otherwise an existing `.blend` (with any hand edits) is only exported. Add a prefab by writing a builder in `tools/blender_street_kit.py` and mapping a source tag to it in `tools/street_furniture.py`.
