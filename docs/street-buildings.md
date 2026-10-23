# Modelling a street's buildings from photos

London Street's 42 buildings were made this way: each building was described by hand from street photos, and the
description, together with LiDAR measurements, was turned into a Blender model by script. This is the process for
doing the same on another street. Run every command from `lyttelton-world/`.

What is **measured** for you, from LINZ 1 m LiDAR (Christchurch 2024-25) and OSM: the footprint and the facade
facing the street, footpath and ground levels, the facade line (OSM footprints are often 1–2 m off; two-storey
facades are registered to the LiDAR roof edge), roof form and pitch, eave and parapet heights, a lower rear
section, and verandah depth and height. What is **described by hand**, from photos: everything you can see on
the facade (storeys, cladding, colours, parapet shape, windows, shopfront, verandah, signs).

Requirements: Blender (found at `/Applications/Blender.app`, on `PATH`, or `$BLENDER`), the prepared world
(`npm run data`) and the Python environment in `.venv`.

## 1. Start the street

```sh
npm run buildings -- --name oxford --init "Oxford Street"
```

`--name` is a short file name you choose; the quoted name is the street exactly as OSM names it. This writes
`buildings/oxford.json` with one entry per building with an edge facing the street within 12 m (skipping any
building another street spec already has), in order along the street. Each entry already builds: it holds a
*typical* facade for the building's type (house, shop, outbuilding…), marked `"evidence": "Not yet observed…"`,
and a `photo` block saying where to photograph it from (the far side of the street, 3 m past the centreline,
facing the facade), with a Mapillary link.

## 2. Photograph each building

Sources, best first:

1. **Your own photos**, taken from each entry's `photo` point. Straight-on, the whole facade in frame, plus a
   close-up of signs. Also upload them to Mapillary if you can: they then help with street furniture too.
2. **Mapillary** (CC BY-SA 4.0): open the entry's `mapillary` link. Coverage of Lyttelton is thin (61 photos
   from 2018 near London Street).
3. **Wikimedia Commons** (search the street name; check each file's licence and date).
4. **Google Street View** was used for London Street, for reference. Google's Maps/Earth terms restrict using
   its imagery to create or augment mapping datasets, so prefer the sources above for new streets.

Note each photo's source and date; it goes in `evidence`.

## 3. Describe each building

For each entry in `buildings/<name>.json`, replace the typical values with what the photos show, and set
`evidence` to the photos used (e.g. `"Own photos 2026-11-02; Commons: <file name> (CC BY 4.0)"`). Remove the
`photo` block when done if you like; it is not used by the build. A worked example, Harbour Co-op on London Street:

```json
{
  "id": "way/101185451", "name": "Harbour Co-op (12 London Street)",
  "evidence": "Street View Apr 2025",
  "storeys": 2, "roof": "hip",
  "wall": {"cladding": "weatherboard", "colour": "#dcc37c"}, "trim": "#2f5a3c",
  "eaves": 0.35,
  "upper": {"windows": 4, "type": "sash"},
  "shopfront": {"bays": 3, "door": 0.38, "frame": "#2f5a3c", "stall": "#dcc37c"},
  "verandah": {"type": "sloped", "posts": true, "post": "#2f4a35", "fascia": "#2f4a35", "fasciaHeight": 0.45,
               "text": "HARBOUR  CO-OP     ORGANIC & WHOLEFOODS", "textColour": "#e9dfc0", "colour": "#a9acaa"}
}
```

Read colours off the photo by eye (pick the lit side of the wall; hex sRGB). Positions along the facade
(`door`, `at`, segment `width`) are fractions of the facade from **left to right as seen from the street**.
Heights are never entered: they come from the LiDAR. The field reference is below; `buildings/london.json` has
42 examples, including shaped parapets with lettering (J. Voyce & Co, J.D. Bundy), a gable bay beside a false
front (`segments`), a roof deck (Eruption Brewing), roller doors (Ambulance Station), twin gables
(71 London Street) and an open canopy.

## 4. Measure, build and check

```sh
npm run buildings -- --name oxford --measure   # print each building's measurements
npm run buildings -- --name oxford             # build buildings/oxford.blend and public/buildings/oxford.glb
npm run buildings -- --name lyttelton          # rebuild the typed town so it leaves these buildings out
```

The build adds the street to `public/buildings/index.json`, which the viewer reads: reload `npm run dev`. Check
each building against its photos at street level (*Walk*, or orbit close) and from above; click a building to
see its name and evidence. Common fixes:

| What you see | Fix in the entry |
|---|---|
| Facade set back from or poking past its neighbours | `"facadeShift": <m>` (positive moves it back into the footprint) |
| Wrong roof form (measure shows a poor RMS) | `"roof": "hip" \| "gable" \| "gable-end" \| "shed" \| "flat"` |
| Tower or wing with its own roof | `"parts": [{"box": [W, S, E, N], "roof": "flat"}]` (local metres) |
| Two gables side by side | `"gables": 2` |
| The OSM polygon is the wrong one (e.g. a porch) | Model the right footprint; list others it covers in `"replaces"` |
| Faces a different street | `"street": "Other Street"` |

Hand edits in Blender are possible too: open `buildings/<name>.blend`, edit, save, then
`npm run buildings -- --name <name> --export` exports it without rebuilding. A plain build regenerates the
`.blend` from the JSON and discards hand edits, so prefer changing the JSON.

## 5. Kerbs, footpaths and furniture (optional)

- **Kerbs and footpaths** need a street inventory of the street (`npm run inventory -- --name <name> --bounds W S E N`;
  see the README): `npm run street -- --name <name> --street "Oxford Street"`. Kerbs come from its parked cars
  and zebra crossings, footpaths reach the facades measured above.
- **Street furniture**: `npm run furniture -- --name <name> --bounds W S E N` places the kit from OSM, council
  asset registers and Mapillary over that area.

Both register themselves with the viewer the same way (`public/streets/index.json`, `public/street-kit/index.json`).

## Field reference

All colours are `"#rrggbb"`. Fractions run 0–1 along the facade, left to right from the street.

| Field | Meaning |
|---|---|
| `id` | OSM id of the footprint, e.g. `"way/101185451"` (from `--init`, or click the building in the viewer) |
| `name`, `evidence` | Shown in the viewer's inspector. `evidence`: the photos the description comes from |
| `street` | OSM street the facade faces (default London Street; `--init` sets it) |
| `storeys` | 1 or 2 (3 for civic). Upper windows go on storey 2 |
| `roof` | Force a roof form instead of the best LiDAR fit: `flat`, `shed`, `gable` (ridge along the street), `gable-end` (gable faces the street), `hip`, or `dsm` (raw heightfield) |
| `roofColour`, `roofMaterial` | Override the aerial roof colour; `roofMaterial`: `corrugated` (default) or `seam` |
| `eaves` | Eave overhang in metres on pitched roofs (default 0.3) |
| `wall` | `{"cladding": weatherboard \| board \| corrugated \| render \| tile, "colour"}`. `tile` also serves as brick |
| `trim` | Window frames, caps, pilasters, barge boards |
| `parapet` | False front: `{"shape": flat \| arch \| gable \| stepped, "above": m above the roof, "rise": arch rise m, "pitch": gable degrees, "text", "text2" (second line), "textColour", "barge"}` |
| `segments` | Facade split left to right, each `{"width": fraction, "parapet", "windows", "windowType", "hood", "sign"}` |
| `upper` | Upper-storey windows `{"windows": n, "type": sash \| single \| pair \| louvre, "pairs": [indices that are pairs], "hood": true, "colour": louvre colour}` |
| `lower` | Ground-floor windows and door (houses) `{"windows": n, "type", "door": fraction, "doorColour", "hood"}` |
| `shopfront` | `{"bays": panes, "door": fraction, "frame", "stall" (riser colour), "stallMaterial": tile, "transom": true, "glazed": taller glass}` |
| `garages` | Roller/garage doors `[{"at": fraction, "width": m, "height": m, "colour", "windows": true}]` |
| `verandah` | `{"type": flat \| sloped, "posts": true, "post", "fascia", "fasciaHeight": m, "colour" (sloped roof), "text", "textColour", "brackets": true, "panels": [{"at", "width", "colour", "text", "textColour"}], "depth", "height"}`. Depth and height default to the LiDAR measurement |
| `sign` | Board on the facade above the verandah `{"text", "colour", "textColour", "width": fraction}` |
| `frieze` | Lettered band under the eave `{"text", "textColour"}` |
| `mural` | Painted watermelon slice (J.D. Bundy) `{"at": fraction, "colour", "rind"}` |
| `deck` | Roof deck with balustrade under a canopy `{"railing", "canopy"}` |
| `brackets` | Eave brackets on the facade (`true`) |
| `open` | Open-sided canopy on posts (`true`), no walls |
| `parts`, `gables`, `facadeShift`, `replaces` | See the fixes table above |
