import {test,expect} from '@playwright/test';
test('real scenery, layers, navigation, building inspection and desktop capture',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  const external:string[]=[];page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5173')&&!r.url().startsWith('blob:http://127.0.0.1:5173')&&!r.url().startsWith('data:'))external.push(r.url());});
  await page.goto('/');
  await page.waitForFunction(()=>Boolean((window as any).__world?.ready));
  await page.waitForFunction(()=>(window as any).__world.tiles.size===100,{},{timeout:120000});
  expect(await page.locator('#data-summary').innerText()).toContain('10 × 10 km');
  const initial=await page.evaluate(()=>({tiles:(window as any).__world.tiles.size,triangles:(window as any).__world.renderer.info.render.triangles,buildings:(window as any).__world.manifest.stats.buildings}));
  expect(initial.buildings).toBeGreaterThan(50);expect(initial.triangles).toBeGreaterThan(10000);
  const vegetation=await page.evaluate(()=>{
    const w=(window as any).__world;let count=0,chunks=0;
    w.scene.traverse((o:any)=>{if(o.name==='Vegetation canopy'){count+=o.count;chunks++;}});
    return{count,chunks,expected:w.manifest.stats.trees,coverage:w.manifest.surface.coverage?.crownCoverageFraction};
  });
  expect(await page.evaluate(()=>(window as any).__world.manifest.surface.landscapeControls)).toBe('landscape-controls.png');
  expect(await page.evaluate(()=>(window as any).__world.manifest.surface.terrainRelief)).toBe('terrain-relief.png');
  expect(vegetation.count).toBe(vegetation.expected);expect(vegetation.chunks).toBeGreaterThan(20);expect(vegetation.coverage).toBeGreaterThan(.8);
  const withVegetation=await page.evaluate(()=>(window as any).__world.renderer.info.render.triangles);
  await page.locator('#vegetation').uncheck();await page.waitForTimeout(300);
  expect(await page.evaluate(()=>(window as any).__world.renderer.info.render.triangles)).toBeLessThan(withVegetation*.7);
  await page.locator('#vegetation').check();
  await expect(page.locator('#imagery')).not.toBeChecked();
  expect(await page.evaluate(()=>[...(window as any).__world.tiles.values()].every((t:any)=>t.mesh.material.map===null&&t.mesh.material.userData.terrainState.referenceMode.value===0))).toBe(true);
  await page.screenshot({path:'.impeccable/review/desktop.png'});
  await page.locator('#imagery').check();
  expect(await page.evaluate(()=>[...(window as any).__world.tiles.values()].every((t:any)=>t.mesh.material.map===t.texture))).toBe(true);
  await page.screenshot({path:'.impeccable/review/reference.png'});
  await page.locator('#buildings').uncheck();await page.locator('#buildings').check();
  await page.locator('#imagery').uncheck();await page.locator('#wireframe').check();
  expect(await page.evaluate(()=>[...(window as any).__world.tiles.values()].every((t:any)=>t.mesh.material.wireframe&&t.mesh.material.map===null))).toBe(true);
  await page.locator('#imagery').uncheck();await page.locator('#wireframe').uncheck();
  await page.locator('[data-view="town"]').click();await page.waitForTimeout(1600);
  await page.screenshot({path:'.impeccable/review/town.png'});
  // Find a visible roof and exercise the same raycast the user gets on click.
  const points=await page.evaluate(()=>{
    const w=(window as any).__world,roofs=w.scene.children.flatMap((g:any)=>g.children??[]).find((m:any)=>m.name==='Building roofs');
    const a=roofs.geometry.attributes.position,points=[];
    for(let i=0;i<a.count;i+=3){const p=w.camera.position.clone().set((a.getX(i)+a.getX(i+1)+a.getX(i+2))/3,(a.getY(i)+a.getY(i+1)+a.getY(i+2))/3,(a.getZ(i)+a.getZ(i+1)+a.getZ(i+2))/3).project(w.camera);if(p.z<1&&Math.abs(p.x)<.7&&Math.abs(p.y)<.7)points.push({x:(p.x+1)*innerWidth/2,y:(1-p.y)*innerHeight/2});if(points.length>=70)break;}return points;
  });
  let picked=false;for(const p of points){if(p.x<300||p.x>1100)continue;await page.mouse.click(p.x,p.y);if(await page.locator('#inspector').isVisible()){picked=true;break;}}
  expect(picked).toBe(true);await expect(page.locator('#building-details')).toContainText('Height source');await page.locator('#close-inspector').click();
  await page.locator('#fly').click();await expect(page.locator('#fly')).toHaveAttribute('aria-pressed','true');
  const before=await page.evaluate(()=>(window as any).__world.camera.position.toArray());await page.keyboard.down('KeyW');await page.waitForTimeout(450);await page.keyboard.up('KeyW');
  const after=await page.evaluate(()=>(window as any).__world.camera.position.toArray());expect(after).not.toEqual(before);
  await page.locator('#reset').click();await page.waitForTimeout(1200);await expect(page.locator('#orbit')).toHaveAttribute('aria-pressed','true');
  await page.locator('#sources-toggle').click();await expect(page.locator('#sources')).toContainText('measured surface heights');
  await page.evaluate(()=>{const w=(window as any).__world,t=w.tiles.get('3-3'),h=t.heights[50*101+50];w.camera.position.set(-1500,h+12,-1500);w.controls.target.set(-1400,h-5,-1300);w.controls.update();});
  await page.waitForTimeout(900);await page.screenshot({path:'.impeccable/review/ground.png'});
  // Move far across the region: distant tiles must release their GPU resources.
  await page.evaluate(()=>{const w=(window as any).__world;w.camera.position.set(-7500,1500,-7500);w.controls.target.set(-4500,200,-4500);w.controls.update();});await page.waitForTimeout(1800);
  expect(await page.evaluate(()=>(window as any).__world.tiles.size)).toBeLessThan(90);
  expect(errors).toEqual([]);expect(external).toEqual([]);
  console.log(JSON.stringify({initial,externalRequests:external.length,errors}));
});
test('phone controls and capture',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto('/');await page.waitForFunction(()=>Boolean((window as any).__world?.ready));await page.waitForFunction(()=>(window as any).__world.tiles.size===100,{},{timeout:120000});
  await expect(page.locator('#panel-content')).toBeHidden();expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);await page.screenshot({path:'.impeccable/review/mobile.png'});
  await page.locator('#panel-toggle').click();await expect(page.locator('#panel-content')).toBeVisible();await page.locator('#sources-toggle').click();await expect(page.locator('#sources')).toBeVisible();
});
test('missing manifest gives a useful recovery action',async({page})=>{
  await page.route('**/world/manifest.json',route=>route.fulfill({status:404,body:'Missing'}));await page.goto('/');await expect(page.locator('#loading-title')).toHaveText('Local world data is not ready');await expect(page.locator('#loading-detail')).toContainText('npm run data');await expect(page.locator('#retry')).toBeVisible();
});
test('a failed nearby tile remains visible as a recoverable error',async({page})=>{
  await page.route('**/world/tiles/7-9.f32',route=>route.fulfill({status:404,body:'Missing'}));await page.goto('/');
  await expect(page.locator('#loading-title')).toHaveText('Some terrain could not load',{timeout:60000});
  await page.waitForFunction(()=>Boolean((window as any).__world?.ready));await expect(page.locator('#loading')).toBeVisible();await expect(page.locator('#retry')).toBeVisible();
});

test('terrain waits for delayed scene data before streaming',async({page})=>{
  const errors:string[]=[];page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/world/features.json',async route=>{await new Promise(resolve=>setTimeout(resolve,1200));await route.continue();});
  await page.goto('/');await page.waitForFunction(()=>Boolean((window as any).__world?.ready));
  expect(errors).toEqual([]);await expect(page.locator('#retry')).toBeHidden();
});

test('credited native model replaces nearby proxies and releases them at distance',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto('/');await page.waitForFunction(()=>Boolean((window as any).__world?.ready));
  await page.waitForFunction(()=>(window as any).__world.nativePlants.state==='ready');
  await page.locator('#native-plant-view').click();
  await page.waitForFunction(()=>(window as any).__world.nativePlants.active>0);await page.waitForTimeout(900);
  const result=await page.evaluate(()=>{
    const w=(window as any).__world,models:any[]=[];w.scene.traverse((o:any)=>{if(o.name.startsWith('Native plant:'))models.push(o);});
    return{active:w.nativePlants.active,parts:models.length,instances:models.reduce((a,m)=>a+m.count,0),bounds:models.every(m=>m.boundingSphere?.radius>0),species:w.nativePlants.species,nativeActive:w.nativePlants.nativeActive,triangles:w.nativePlants.triangles,representative:w.nativePlants.representativeModels};
  });
  expect(result.nativeActive).toBeGreaterThan(0);expect(result.nativeActive).toBeLessThanOrEqual(48);expect(result.instances).toBe(result.nativeActive*10);expect(result.representative).toBe(10);expect(result.triangles).toBeLessThanOrEqual(6_000_000);expect(result.parts).toBe(10);expect(result.active).toBeGreaterThan(0);expect(result.active).toBeLessThanOrEqual(2000);expect(result.instances).toBeGreaterThan(0);expect(result.bounds).toBe(true);
  await page.screenshot({path:'.impeccable/review/native-plants.png'});
  await page.setViewportSize({width:390,height:844});await page.locator('#panel-toggle').click();await page.screenshot({path:'.impeccable/review/native-plants-mobile.png'});await page.setViewportSize({width:1440,height:1000});await page.locator('#panel-toggle').click();
  await page.locator('#sources-toggle').click();await expect(page.locator('#sources')).toContainText('PlantCatalog (CC-BY-4.0)');await expect(page.locator('#native-plant-info')).toContainText('Species placement is illustrative');
  await page.locator('#vegetation').uncheck();expect(await page.evaluate(()=>(window as any).__world.scene.getObjectByName('Native plant models').parent.visible)).toBe(false);await page.locator('#vegetation').check();
  await page.locator('#reset').click();await page.waitForTimeout(1800);expect(await page.evaluate(()=>(window as any).__world.nativePlants.active)).toBe(0);
  expect(errors).toEqual([]);
});

test('missing plant assets preserve generated vegetation and navigation',async({page})=>{
  await page.route('**/plants/**/*.glb',route=>route.fulfill({status:404,body:'Missing'}));
  await page.route('**/*ez-tree*',route=>route.fulfill({status:404,body:'Missing'}));
  await page.goto('/');await page.waitForFunction(()=>Boolean((window as any).__world?.ready));
  await page.waitForFunction(()=>(window as any).__world.nativePlants.state==='unavailable');
  await expect(page.locator('#native-plant-view')).toHaveCount(0);await expect(page.locator('#retry')).toBeHidden();
  expect(await page.evaluate(()=>(window as any).__world.nativePlants.active)).toBe(0);
});

test('procedural foliage survives a missing named species without an empty shortcut',async({page})=>{
  await page.route('**/plants/cc-by/*.glb',route=>route.fulfill({status:404,body:'Missing'}));
  await page.goto('/');await page.waitForFunction(()=>Boolean((window as any).__world?.ready));
  await page.waitForFunction(()=>(window as any).__world.nativePlants.state==='ready');
  expect(await page.evaluate(()=>(window as any).__world.nativePlants.representativeModels)).toBe(10);
  await expect(page.locator('#native-plant-view')).toHaveCount(0);await expect(page.locator('#retry')).toBeHidden();
});
