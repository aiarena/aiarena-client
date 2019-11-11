'use strict';

const electron = require('electron');
const app = electron.app;
const BrowserWindow = electron.BrowserWindow;
const path = require('path');

// This method will be called when Electron has finished
// initialization and is ready to create browser mainWindow.
// Some APIs can only be used after this event occurs.
var rq = require('request-promise');
var mainWindow = null;
var mainAddr = 'http://127.0.0.1:8080/';


// spawn server and call the child process
var child = require('child_process').spawn('python', ['server.py'],{
    detached: true, 
    stdio: 'ignore',
    cwd: '../'
  }, function(err, data) {
    if(err){
      console.error(err);
      return;
    }
    console.log(data.toString());
  });
function createWindow(){


    // Create the browser mainWindow
    mainWindow = new BrowserWindow({
      minWidth: 600,
      minHeight: 550,
      show: false
    });
  
    // Load the index page of the flask in local server
    mainWindow.loadURL(mainAddr);
  
    // ready the window with load url and show
    mainWindow.once('ready-to-show', () => {
      mainWindow.show();
    });
  
    // Quit app when close
    mainWindow.on('closed', function(){
      mainWindow = null;
      // kill the server on exit
      child.unref();
    });
    // (some more stuff, eg. dev tools) skipped... 
  };
  
  var startUp = function(){
    rq(mainAddr)
      .then(function(htmlString){
        console.log('server started!');
        createWindow();
      })
      .catch(function(err){
        console.log('waiting for the server start...');
        startUp();
      });
  };
  
  app.on('ready', startUp)
  
  app.on('quit', function() {
      // kill the python on exit
      child.kill();
  });
  
  app.on('window-all-closed', () => {
      // quit app if windows are closed
      if (process.platform !== 'darwin'){
          app.quit();
      }
  });