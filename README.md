# aiarena-client
## Bootstrapping for local play on windows
The linux steps are probably essentially the same, I just can't guarantee they'd work because I haven't tested it.

#### Clone this repo
A recursive clone is required in order to download all the test bots.  
`git clone --recursive https://github.com/aiarena/aiarena-client.git`

If you already have the repo cloned but didn't do a recursive clone, run the following:  
`git submodule update --init --recursive`

#### 1. Install pip requirements

```
pip install -r requirements.windows.txt
```
#### 2. Run the GUI server

Run the following code in the root of the repo:
```
python setup.py install
```

Then you can start the GUI server with:
```
python -m arenaclient -f
```

#### 3. Access the GUI server

In your browser navigate to:

`127.0.0.1:8765`

Click on `settings` and set up all the settings to your preference. After you click submit, you will be refirected to the
home page, where you can select your bots and maps you want to run.
Click on `Play` and the game should start within a few seconds.



## License

Copyright (c) 2019

Licensed under the [GPLv3 license](LICENSE).
