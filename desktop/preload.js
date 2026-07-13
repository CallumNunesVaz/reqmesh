// Preload runs with Node integration but in an isolated context. reqmesh's UI
// is a plain web app that talks to the local backend over HTTP, so there's no
// privileged bridge to expose yet — we just surface a tiny marker the renderer
// can use to detect it's running inside the desktop shell.
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('reqmesh', {
  desktop: true,
  platform: process.platform,
});
