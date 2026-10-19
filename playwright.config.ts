import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests/browser',timeout:120000,workers:1,use:{baseURL:'http://127.0.0.1:5173',viewport:{width:1440,height:1000},launchOptions:{executablePath:process.env.PLAYWRIGHT_CHROME??'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--use-angle=metal']}}});
