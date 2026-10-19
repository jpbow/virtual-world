import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const out=process.env.COMPARE_OUT??'reports/comparison';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROME??'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--use-angle=metal']});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
await page.goto('http://127.0.0.1:5173');
await page.waitForFunction(()=>window.__world?.ready);
await page.waitForFunction(()=>window.__world.tiles.size===100,{},{timeout:120000});
const results=[];
for(const name of ['harbour','town','hills','diamond']){
  await page.locator(`[data-view="${name}"]`).click({force:true});
  await page.waitForTimeout(800);
  for(const [mode,reference,objects] of [['generated',false,true],['aerial',true,false]]){
    for(const id of ['imagery','buildings','roads','vegetation'])await page.locator(`#${id}`).setChecked(id==='imagery'?reference:objects,{force:true});
    await page.waitForTimeout(300);
    await page.screenshot({path:`${out}/${name}-${mode}.png`});
  }
  results.push({name,camera:await page.evaluate(()=>({position:window.__world.camera.position.toArray(),target:window.__world.controls.target.toArray()}))});
}
await writeFile(`${out}/views.json`,JSON.stringify(results,null,2));
await writeFile(`${out}/index.html`,`<!doctype html><meta charset="utf-8"><title>Aerial / geometry comparison</title><style>body{font:16px system-ui;background:#eee;margin:24px}section{margin-bottom:36px}div{display:flex;gap:8px}figure{margin:0;flex:1}img{width:100%}h1{font-size:24px}</style><h1>Matched aerial / generated comparisons</h1><p>Identical camera per pair. Aerial captures hide reconstructed buildings, roads and vegetation to expose source evidence. Generated ground uses procedural materials.</p>${results.map(({name})=>`<section><h2>${name}</h2><div>${['aerial','generated'].map(mode=>`<figure><figcaption>${mode}</figcaption><img src="${name}-${mode}.png"></figure>`).join('')}</div></section>`).join('')}`);
await browser.close();
console.log(`Saved matched comparisons to ${out}/index.html`);
