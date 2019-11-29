# aiarena-client
## Bootstrapping for local play on windows
The linux steps are probably essentially the same, I just can't guarantee they'd work because I haven't tested it.

#### Clone this repo
A recursive clone is required in order to download all the test bots.  
`git clone --recursive https://gitlab.com/aiarena/aiarena-client.git`

If you already have the repo cloned but didn't do a recursive clone, run the following:  
`git submodule update --init --recursive`

#### 1. Install pip requirements

```
pip install -r requirements.windows.txt
# temp fix
pip install --upgrade  git+https://github.com/Dentosal/python-sc2@develop
```

#### 1. Set SC2PATH
Create an `SC2PATH` environment variable that points to the sc2 install location.  
The default for windows is `C:\Program Files (x86)\StarCraft II\`

#### 2. Create a config
The `/arenaclient/default_config.py` file stores all the default config values that will be used when running the arena client. You can override any of these values in a `/arenaclient/config.py` file.

An example local config is available at  `/arenaclient/example_local_config.py`.

#### 3. Copy the test bots
Copy the test bots from `/aiarena-test-bots/` into your configured `BOTS_DIRECTORY`. This would be `/arenaclient/bots` if you're using the example config.

#### 4. Matches file
The matches file lists the matches to be played.  
Make a copy of the `/arenaclient/example_matches` file as `/arenaclient/matches`.

#### 5. Run a match
Navigate to the containing cloned repo and start the client with
```
python -m arenaclient
```
This should run a match between `basic_bot` and `loser_bot`.


## License

Copyright (c) 2019

Licensed under the [GPLv3 license](LICENSE).