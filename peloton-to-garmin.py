#
# Author: Bailey Belvis (https://github.com/philosowaffle)
#
# Tool to generate a valid TCX file from a Peloton activity for Garmin.
#
import os
import sys
import json
import logging
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import sqlite3

from lib import pelotonApi
from lib import config_helper as config
from lib import tcx_builder
from lib import garminClient
from lib import db_utils

##############################
# Debugging Setup
##############################
if config.ConfigSectionMap("DEBUG")['pauseonfinish'] is None:
    pause_on_finish = "false"
else:
    pause_on_finish = config.ConfigSectionMap("DEBUG")['pauseonfinish']

##############################
# Logging Setup
##############################
if len(sys.argv) > 3:
    file_handler = logging.FileHandler(sys.argv[3])
else:
    if config.ConfigSectionMap("LOGGER")['logfile'] is None:
        logger.error("Please specify a path for the logfile.")
        sys.exit(1)
    file_handler = logging.FileHandler(config.ConfigSectionMap("LOGGER")['logfile'])

logger = logging.getLogger('peloton-to-garmin')
# logger.setLevel(logging.DEBUG)
logger.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s: %(message)s')

# File Handler
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

logger.debug("Peloton to Garmin Magic :)")

##############################
# Environment Variables Setup
##############################
if os.getenv("NUM_ACTIVITIES") is not None:
    numActivities = os.getenv("NUM_ACTIVITIES")
else:
    #numActivities = None
    numActivities = 10

if os.getenv("OUTPUT_DIRECTORY") is not None:
    output_directory = os.getenv("OUTPUT_DIRECTORY")
else:
    output_directory = config.ConfigSectionMap("OUTPUT")['directory']
    # Create directory if it does not exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

##############################
# Peloton Setup
##############################

if len(sys.argv) > 2:
    peloton_email = sys.argv[1]
    peloton_password = sys.argv[2]
else :
    if config.ConfigSectionMap("PELOTON")['email'] is None:
        logger.error("Please specify your Peloton login email in the config.ini file.")
        sys.exit(1)

    if config.ConfigSectionMap("PELOTON")['password'] is None:
        logger.error("Please specify your Peloton login password in the config.ini file.")
        sys.exit(1)

    peloton_email = config.ConfigSectionMap("PELOTON")['email']
    peloton_password = config.ConfigSectionMap("PELOTON")['password']

api = pelotonApi.PelotonApi(peloton_email, peloton_password)

##############################
# Main
##############################
if numActivities is None:
    numActivities = input("How many past activities do you want to grab?  ")

logger.info("Get latest " + str(numActivities) + " workouts.")
workouts = api.getXWorkouts(numActivities)

garmin_email = config.ConfigSectionMap("GARMIN")['email']
garmin_password = config.ConfigSectionMap("GARMIN")['password']

for idx, w in enumerate(workouts):
    workoutId = w["id"]
    logger.info("Get workout: " + str(workoutId))

    # Check to see if the workout ID has already been logged in the database
    con = db_utils.db_connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM workouts WHERE workoutID='"+str(workoutId)+"'")
    (workoutCount,) = cur.fetchone()
    con.close()

    # Check to see if the count of the workout ID in the database is greater than 0
    if workoutCount > 0:
        if idx != len(workouts) - 1:
            logger.info(str(workoutId + " has alreday been uploaded, moving on to the next file!"))
        else:
            logger.info(str(workoutId) + " has already been uploaded and is the last file, so this process will exit. Bye!")
            sys.exit()

    # If the workout ID does not exist in the database, create the file and upload to Garmin
    else:
        workout = api.getWorkoutById(workoutId)

        logger.info("Get workout samples")
        workoutSamples = api.getWorkoutSamplesById(workoutId)

        logger.info("Get workout summary")
        workoutSummary = api.getWorkoutSummaryById(workoutId)

        logger.info("Writing TCX file")
        try:
            title, filename = tcx_builder.workoutSamplesToTCX(workout, workoutSummary, workoutSamples, output_directory)
        except Exception as e:
            logger.error("Failed to write TCX file for workout {} - Exception: {}".format(workoutId, e))

        activityType = "cycling"

        fileToUpload = [output_directory + "/" + filename]

        garminClient.uploadToGarmin(fileToUpload, garmin_email, garmin_password, str(activityType), title)

        # Add information to SQLite
        cur = con.cursor()
        workout_sql = "INSERT INTO workouts (workoutID, title, filename) VALUES (?, ?, ?)"
        cur.execute(workout_sql, (workoutId, title, filename))
        con.commit()
        con.close()
    

logger.info("Done!")
logger.info("Your Garmin TCX files can be found in the Output directory: " + output_directory)

if pause_on_finish == "true":
    input("Press the <ENTER> key to continue...")
