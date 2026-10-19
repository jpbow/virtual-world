---
name: Lyttelton viewer
description: A landscape-first operating surface for a measured geographic world.
colors:
  paper: "#f3f1e7"
  ink: "#153c3c"
  muted: "#486361"
  accent: "#245c50"
  control: "#193f40"
  control-text: "#faf7eb"
  selected: "#dce5d7"
  hover: "#e3e7db"
  line: "#cbd0c2"
  focus: "#a35525"
  scene-grass-deep: "#71765b"
  scene-grass-dry: "#99977b"
  scene-growing-grass: "rgb(15% 20% 9%)"
  scene-canopy-floor: "rgb(7.5% 9.5% 5.5%)"
  scene-rock: "#8d8b7c"
  scene-soil: "#846b4d"
  scene-paving: "#747b7a"
  scene-trunk: "#6e6550"
  scene-water: "#457c80"
  scene-selection: "#f3c45e"
  scene-mesh-base: "#ffffff"
typography:
  title:
    fontFamily: 'Georgia, "Times New Roman", serif'
    fontSize: "29px"
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Avenir Next", Avenir, system-ui, sans-serif'
    fontSize: "14px"
  label:
    fontFamily: '"Avenir Next", Avenir, system-ui, sans-serif'
    fontSize: "11px"
    fontWeight: 650
    letterSpacing: "0.06em"
rounded:
  square: "0px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
  inset: "28px"
components:
  panel-toggle:
    backgroundColor: "{colors.control}"
    textColor: "{colors.control-text}"
    rounded: "{rounded.square}"
    padding: "16px"
  view-button:
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "9px 5px"
  view-button-selected:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.ink}"
  navigation-active:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    padding: "8px"
  panel:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    width: "252px"
---

# Design System: Lyttelton viewer

## Overview

**Creative North Star: "A field guide beside the harbour"**

An unobtrusive landscape viewer informed by pale paper, vegetation and harbour colours. The generated geographic world leads; compact controls support exploration and inspection. Aerial evidence guides reconstructed scenery and ground classes, while generated materials cover the photograph by default. Georgia gives the place name an editorial character while the operating interface stays quiet and legible.

**Key Characteristics:**
- Full-viewport generated geographic landscape with optional aerial comparison.
- Opaque paper panels with restrained depth.
- Teal operating controls and clear selected states.
- Visible attribution and inspectable provenance.

## Colors

### Primary

Harbour teal supplies active navigation and checkbox accents. Deep control teal anchors the collapsible panel header. Selected views use pale vegetation green; hover uses a subtle pale wash. Rust supplies the keyboard focus outline.

### Neutral

Paper separates controls from the detailed landscape. Dark ink carries primary text; muted ink carries supporting instructions and sources. The pale line colour divides groups and outlines view buttons. Generated ground materials and evidence-guided scenery supply the surrounding colour variety. Aerial imagery is an optional comparison view.

### Environmental palette

Scene tokens are separate from the interface palette: deep and dry grass, categorical growing-grass darkening, darker canopy floor, neutral rock, warm soil and grey paving supply generated ground; muted brown trunks and harbour water support scenery. Warm gold outlines a selected building. White is a neutral mesh base rather than a visible ground class. Roof colours are sampled per building from aerial evidence, rather than selected from this fixed palette. These scene colours do not replace paper and teal interface roles.

**The Landscape Rule.** Keep interface colour restrained so the geographic scene remains the dominant visual field.

## Typography

The title uses the Georgia stack defined above. Operative text uses Avenir Next with Avenir and system fallbacks. The secondary place name is smaller (23px), and the building inspector heading uses Georgia (22px). Buttons and instructions use compact text (12–13px); source details use smaller text (11px). Fieldset legends use uppercase label styling.

**The Place Name Rule.** Reserve serif type for the place title and building heading; use sans serif for controls, instructions and evidence.

## Layout

The canvas fills the viewport (100svh). The title sits above a narrow left control panel with a separate reset control at the upper right. Desktop side insets use the inset token; the panel begins below the title (147px) and scrolls within the available height. Place shortcuts form two columns. A selected building opens a right-side inspector (275px wide). A slim footer holds orientation, elevation and attribution.

At the phone breakpoint (700px), side insets tighten (14px), title size reduces (24px), the secondary name moves to its own line (17px), and the subtitle hides. The control panel narrows (218px); screens initially narrower than the breakpoint start with its contents collapsed. The inspector moves above the footer and spans the available width. The footer stacks its location and attribution rows. Short desktop screens tighten panel placement and group spacing.

**The Clear View Rule.** Let controls collapse without removing the title, reset action or source attribution.

## Elevation & Depth

Opaque paper surfaces float above the rendered landscape using shallow, diffuse shadows. The title uses the lightest shadow, while operating panels and status messages have slightly stronger separation. Borders divide controls rather than boxing every text block. Depth in the world comes from measured terrain, generated scenery, lighting and distance fog. Ground materials use world-space macro colour variation, fine detail and bump relief, preserving their scale across tile boundaries and distance levels. Nearby ground blends local CC0 grass and forest-floor scans with 1K colour, OpenGL normal and roughness maps, repeating at their recorded physical widths (2.51 m and 2.14 m respectively). Detail fades between 65 m and 220 m into the existing macro colours. Geographic class maps constrain the surface blend, and canopy occupancy selects forest floor. Forest-floor albedo is desaturated and toned down in the shader while source maps remain unchanged. These scans are representative surface samples rather than photographs of the actual Lyttelton ground; existing terrain horizons and hillshade lighting remain in use. Class-only RGB weight maps at 2 m resolution blend grass, rock and soil, with paving as the remaining weight. A separate RGBA landscape control texture carries canopy occupancy, growing-grass category, DEM sky openness and fixed-sun visibility. Growing grass and canopy floor darken the generated material; openness modulates indirect light and horizon visibility modulates the fixed sun. Neither control texture carries aerial RGB. Grass condition is a categorical estimate and can misclassify shaded or dry ground. Published LINZ 1 m DEM hillshade is cached at 2 m; a local ratio removes broad fixed-direction shading before its fine relief is used as 5 m lighting detail, reducing double lighting with the 3D sun. Optional missing hillshade produces neutral detail. This changes lighting, while the finest terrain mesh remains 10 m. A coarse measured terrain base covers the full world while detailed tiles stream, preserving a continuous landscape during loading.

Vegetation renders in one-kilometre chunks. Nearby crowns retain fuller geometry and trunks; distant chunks use cheaper crown geometry without trunks, sharing the placement and colour buffers. Low scrub follows the terrain slope so its mass rests against the ground, and its rendered coverage is clipped to measured canopy occupancy; taller crowns can overhang. Conservative slope-aware footprint coverage checks measure how much of the detected vegetation mask the rendered clusters cover; they do not measure classification accuracy. One actual textured PlantCatalog tī kōuka / cabbage-tree model (Cordyline australis), licensed CC BY 4.0, replaces a limited subset of nearby generated proxies. Detailed models render within 180 m, capped at 48 instances, on a deterministic 2.5% subset of height-compatible vegetation (3.5–9 m). Species assignment is illustrative rather than aerial identification. Ten representative tree and bush variants generated with EZ-Tree (MIT) replace nearby other tree and scrub proxies: trees within 150–170 m, bushes within 75 m. These are representative forms, not verified New Zealand native species. Compatible cabbage-tree assignments take precedence over representative variants. The detailed foliage budget is 2,000 total instances and 6 million submitted triangles inside a widened view cone, with the named species still capped at 48. Trees fit LiDAR height and loosely follow crown width; each low-scrub cluster is filled with several bushes aligned to the terrain. Distant, unavailable and over-budget plants retain generated proxies. This limited asset set does not constitute a complete flora library.

## Shapes

Panels and buttons have square corners. Thin borders define place shortcuts and segmented navigation. Native checkboxes remain familiar. Only the loading spinner and tiny status dot are circular. Disclosure and close marks are authored SVG strokes; the north marker is a filled SVG arrow that turns with the camera.

## Components

### Operating panel

The dark panel toggle spans the full width, with a minus mark when expanded and plus mark when collapsed. Its state is exposed with `aria-expanded`. Within the paper panel, fieldsets group destinations, navigation and layer controls. Sources expand beneath the data summary.

### Buttons and navigation

Place shortcuts use thin neutral outlines, teal borders and a pale fill when selected. A full-width Native plants shortcut appears within the same destination group only after a model loads. It chooses an inspection angle using terrain, neighbouring crown and building occlusion checks, without hiding surrounding scenery. Orbit and Fly share a segmented control; the active segment uses teal with white text. The reset action uses a paper surface. Hover slightly darkens buttons, with a pale fill on place shortcuts. Keyboard focus uses a visible rust outline (3px) with spacing from the control (3px). Disabled buttons fade and show a waiting cursor.

### Layer controls

Native checkboxes use the teal accent, aligned with concise labels. Each label provides a clickable row. Terrain wireframe, Aerial reference, buildings, roads and woodland remain independently controlled. Aerial reference starts unchecked: generated grass, rock, soil and paving are the default, and checking the control displays the photograph for comparison.

### Evidence and feedback

The inspector uses a serif heading, compact definition list and procedural-wall note. Ground classification is an explicit RGB/height heuristic constrained by OSM geometry; it is not a trained semantic model. LiDAR canopy peaks seed vegetation placement; evidence-based coverage fill supplies overlapping crown and low-scrub clusters between peaks. Mapped woodland preserves shaded foliage, and the detected mask includes raised vegetation above 0.7 m. Root positions avoid building footprints and mapped roads, while crowns can overhang them. Clusters approximate vegetation mass rather than surveyed individual trees. The prepared world has sampled colours on 13,399 roofs. Facades, tree species and crown shapes remain approximate; sampled roof colours and roof-fit residuals do not establish independently surveyed reconstruction accuracy. Loading and failure states use textual status on paper; failures expose a retry action. Source links and attribution stay readable. Model credits show the author, licence and source link; original assets and attribution remain alongside the prepared world. About this world also links to Poly Haven with CC0 credit for ground and road scans. Motion respects reduced-motion preferences; camera viewpoint transitions become immediate when requested.

## Do's and Don'ts

### Do:
- **Do** keep the landscape visible around compact controls.
- **Do** distinguish measured evidence, heuristic classification and procedural approximations in inspection and source text.
- **Do** show generated ground by default and use Aerial reference for comparison.
- **Do** preserve keyboard focus, reduced motion and responsive control collapse.
- **Do** keep source attribution visible in the footer.

### Don't:
- **Don't** use decorative imagery in place of geographic evidence.
- **Don't** use serif type for routine operating controls.
- **Don't** obscure the scene with unnecessary opaque interface surfaces.
