# Third-party plant credits

**Realistic HD Cabbage tree (18/50)** — Cordyline australis, by **PlantCatalog**.

Source: https://sketchfab.com/3d-models/realistic-hd-cabbage-tree-1850-3d22d3ed01ad4f589b3bfcbcae294407
Author: https://sketchfab.com/PlantCatalog
Licence: **Creative Commons Attribution 4.0 International (CC BY 4.0)** — https://creativecommons.org/licenses/by/4.0/

Downloaded through Sketchfab's authorised download control on 20 October 2026, as its converted GLB with 1K textures. File: `cc-by/cordyline-australis.glb`. Model title specifies maturity preset Wild mat 50; published height 3.9m, 85,160 triangles.

The downloaded file is unmodified. At runtime we normalize its origin and height, scale it to selected LiDAR vegetation heights, instance it, render materials double-sided, and ignore vertex colours whose original purpose is material blending rather than diffuse colour. The original textures and geometry remain in the GLB. Species placement is illustrative; the aerial/height classifier does not identify individual cabbage trees.

## Representative procedural trees and bushes

Nearby trees and bushes other than the cabbage tree are generated in the browser with **EZ-Tree** by Daniel Greenheck (MIT licence): https://github.com/dgreenheck/ez-tree. Its bundled bark and leaf textures ship with the npm package `@dgreenheck/ez-tree`; its bark README credits Poly Haven (CC0) and TextureCan sources.

Ten variants (broadleaf, slender, tall broadleaf, conifer and three bush forms) are generated from the library's presets with denser leaf settings and green leaf textures. These are **representative forms**, not a claim that those species occur at the rendered locations. Runtime fits height to LiDAR vegetation, follows measured crown width only loosely to keep natural proportions, fills low-scrub clusters with several bushes, and tints leaves toward the aerial-sampled crown colour.
