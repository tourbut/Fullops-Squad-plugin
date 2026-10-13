const {firefox}=require('/private/tmp/fullops-completion-z_ii0xr2/runtime/lib/python3.13/site-packages/playwright/driver/package');
const fs=require('fs');
(async()=>{
 const server=await firefox.launchServer({headless:true,executablePath:'/private/tmp/fullops-completion-z_ii0xr2/browsers/firefox-1543/firefox/Nightly.app/Contents/MacOS/firefox',host:'127.0.0.1',timeout:20000});
 fs.writeFileSync(process.argv[2] || '/private/tmp/fullops-completion-z_ii0xr2/firefox-endpoint.txt',server.wsEndpoint());
 console.log('Fresh native-sandbox Firefox broker ready');
 process.on('SIGTERM',async()=>{await server.close();process.exit(0)});
})();
