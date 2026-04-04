The file inside the SEED folder, called tp_showroom_mapping.seed.json, is used by the app as a bridge between iRacing and Trading Paints car names.

Every season, when a new car is released, this file needs to be updated. The easiest way to do this is to download the tp_seed_review_cly.py tool along with the .json file and run it again after the season update. The tool will identify new cars and prompt the user on how to handle them.

Some cars may currently have incorrect names in the .json because iRacing and Trading Paints use different naming conventions. In these cases, you will see an error message in the log stating that there is no paint available in the showroom for {car model}. When this happens, simply open the .json, correct the car name to match the one expected in the log, and compile the app again, or run script.py with the .json file in the same folder.
