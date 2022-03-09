# aiarena-client

## Playing local bot matches

### Just want to run some local bot matches without installing everything?
Try the [aiarena-docker image](https://github.com/aiarena/aiarena-docker) instead.

### Bootstrapping this repo for windows (more complex, more control)

The linux steps are probably essentially the same, I just can't guarantee they'd work because I haven't tested it.

#### Clone this repo
A recursive clone is required in order to download all the test bots.  
`git clone --recursive https://github.com/aiarena/aiarena-client.git`

If you already have the repo cloned but didn't do a recursive clone, run the following:  
`git submodule update --init --recursive`

#### 1. Install pip requirements

```
pip install -r requirements.txt
```

#### 2. Setup

Run the following code in the root of the repo:
```
python setup.py install
```

There are a few things you need to change inside the folders:
1. In `arenaclient/configs/default_local_config.py`, change line 74 to import from relative path:
```
try:
    from .local_config import * # Does not have the "." by default
except ImportError as e:
    ...
```
2. Create a `local_config.py` file in `arenaclient/configs` and override any information found in `default_local_config.py` that do no match your environment. For example:
```
PYTHON='python' # Command used to run Python in your terminal, might be "python3" for some people.
SC2_HOME='C:/Games/StarCraft II' # Path to your SC2 folder
```
3. In `arenaclient/__main__.py`, change `default_config` to `default_local_config`.
4. Copy the `arenaclient/example_matches` file into the `arenaclient/configs` folder and rename it to `matches`.
5. Open your new `matches` file in a text editor and change `AutomatonLE` to the name of any map found in the root for your `StarCraft II/Maps/` folder.
6. Copy the `basic_bot` and `loser_bot` folders from `aiarena-test-bots` into `arenaclient/configs/bots`.

#### 3. Run the server

Then you can start the server with:
```
python -m arenaclient -f
```
This will run the matches listed in the `arenaclient/configs/matches` file, each for 5 times by default (override this using `ROUNDS_PER_RUN` in `local_config.py`). Replays will be saved in `arenaclient/configs/replays/`.

Note: If you receive bot initialization errors, you likely need to install bot dependencies. Error logs can typically be found inside each bot folder such as `arenaclient/configs/bots/basic_bot/data/stderr.log`

## License

Copyright (c) 2019

Licensed under the [GPLv3 license](LICENSE).
