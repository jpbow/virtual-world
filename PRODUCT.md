# Lyttelton world

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
TypeScript, Vite, Three.js; Python and GDAL data pipeline, as approved in the implementation plan.

## Users
The repository owner exploring an initial real-world environment and evaluating automated geographic world building.

## Product Purpose
Explore a recognisable 10 × 10 km world centred on Lyttelton, including the harbour and Port Hills.

## Capabilities and Constraints
Local standalone viewer with orbit and fly navigation, generated ground materials, optional aerial comparison, roads, buildings, vegetation, terrain inspection and data provenance. Use real LINZ elevation and imagery plus OSM features. Building heights and roof shapes should use surface measurements when supported. No game integration, collision, fabricated geographic terrain, paid services or required API keys. Preserve the rest of this repository.

## Evidence on Hand
Public LINZ elevation and imagery catalogs and OpenStreetMap data. Roof fit residuals are recorded, but reconstruction accuracy is not independently surveyed. Ground classification uses RGB/height heuristics constrained by OSM, rather than a trained semantic model. Vegetation uses canopy peaks plus coverage fill, including shaded woodland and low-scrub clusters; instance counts do not represent surveyed individual trees. Ground controls distinguish growing grass and canopy floor; measured DEM horizons add terrain shade. Published LINZ DEM hillshade supplies fine lighting detail, with broad fixed-direction shading removed; it does not add mesh geometry. One free CC BY 4.0 PlantCatalog cabbage-tree model (Cordyline australis) is installed for limited nearby rendering. Species placement is illustrative; nearby other trees and shrubs use representative CC0 broadleaf models, while distant or over-budget vegetation retains generated proxy geometry. These representative models are not verified NZ native species. Close ground uses scanned CC0 grass and forest-floor colour, normal and roughness detail, constrained by geographic surface masks; it does not display the aerial photograph. Facades without photographs are approximations.

## Product Principles
- Geographic evidence determines geometry.
- Imagery guides reconstruction; generated ground surfaces replace the photograph by default.
- Distinguish measurements from procedural defaults.
- Let the landscape occupy the screen; controls support exploration.
- Cache data so the prepared world runs locally.
