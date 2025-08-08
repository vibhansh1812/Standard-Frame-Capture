import datetime
import os
import PySpin
import sys
import shutil
import time 
import subprocess
import multiprocessing
import cv2
import ast
import numpy as np
import xml.etree.ElementTree as ET
import traceback
import logging
from logging import handlers
from logging.handlers import TimedRotatingFileHandler
import shutil
import pymysql
from collections import OrderedDict
from threading import Timer
import json
import paho.mqtt.client as mqtt
debugMode = False 
PROCESS_ID = os.getpid()
BASE_PATH = os.getcwd()
FRAME_PROCESS_ID = os.getpid()

logger = None
gMailObj = None
configHashMap = {}
configObject = OrderedDict()
client = None

# Global variable to store real-time distance from MQTT
conveyorDistance = 0  
''' Process ID and Base Code Path '''
class CONFIG_KEY_NAME:
    CODE_PATH = "CODE_PATH"
    LOG_FILE_PATH = "LOG_FILE_PATH"
    LOG_BACKUP_COUNT = "LOG_BACKUP_COUNT"
    RAW_IMAGE_BOTH = "RAW_IMAGE_BOTH"
    TOP_IMAGE_PATH = "TOP_IMAGE_PATH"
    BOTTOM_IMAGE_PATH = "BOTTOM_IMAGE_PATH"
    FRAME_START_INFO_FILE_PATH = "FRAME_START_INFO_FILE_PATH"
    DB_USER = "DB_USER"
    DB_PASS = "DB_PASS"
    DB_HOST = "DB_HOST"
    DB_NAME = "DB_NAME"
    TOP_CAMERA_ID = "TOP_CAMERA_ID"
    BOTTOM_CAMERA_ID ="BOTTOM_CAMERA_ID"
    SAVE_RAW_IMAGE_FLAG = "SAVE_RAW_IMAGE_FLAG"
    BELT_CYCLE_DURATION = "BELT_CYCLE_DURATION"
    PLC_IP_ADDRESS = "PLC_IP_ADDRESS"
    PLC_WRITE_DB_NUMBER = "PLC_WRITE_DB_NUMBER"
    PLC_READ_DB_NUMBER = "PLC_READ_DB_NUMBER"
    # Read MQTT details
    MQTT_BROKER = 'MQTT_BROKER'
    MQTT_PORT = 'MQTT_PORT'
    MQTT_TOPIC = "MQTT_TOPIC"

Marking_Image="/home/insightzz-conveyor-02/insightzz/Code/FrameCapture/Marking_Images/"
conveyor_status = 0

class RepeatedTimer():
	"""
	Class to set timer
	"""
	def __init__(self, interval, function, *args, **kwargs):
		self._timer = None
		self.interval = interval
		self.function = function
		self.args = args
		self.kwargs = kwargs
		self.is_running = False
		self.start()

	def _run(self):
		"""
		set timer
		"""
		self.is_running = False
		self.start()
		self.function(*self.args, **self.kwargs)
		self.stop()

	def start(self):
		"""Starts the timer if not already running."""
		if not self.is_running:
			self._timer = Timer(self.interval, self._run) # Schedule `_run` function
			self._timer.start()
			self.is_running = True

	def stop(self):
		"""
		stop timer
		"""
		self._timer.cancel()
		self.is_running = False

# Function to check the conveyor status from the database
def take_conveyor_status():
    """
    Fetches the conveyor status from the database and updates the global conveyor_status variable.
    """
    global logger, conveyor_status
    try:
        db_con = None
        cur = None
        db_con = getDatabaseConnection()
        cur = db_con.cursor()
        query = "select * from MANIKGARH_CONVEYOR_DB.CONVEYOR_STATUS_TABLE WHERE (ID = '1');"
        cur.execute(query)
        data_set = cur.fetchall()
        if data_set[0][1] == 1:
            conveyor_status = 1
            logger.info("Conveyor ON")
        elif data_set[0][1] == 0:
            conveyor_status = 0
            logger.info("Conveyor OFF")
    except Exception as e:
        logger.error(f"Error in Db backup : {e}")
    finally:
        logger.info("Timer start")
        timer_st = RepeatedTimer(1 * 10, take_conveyor_status)
        timer_st.start()
        if cur is not None:
            cur.close()
        if db_con is not None:
            db_con.close()


# Function to save image with the current date and timestamp
def save_image_with_timestamp(image, base_path):
    try:
        # Get the current date to create a directory
        current_date = datetime.datetime.now().strftime('%Y_%m_%d')
        date_dir = os.path.join(base_path, current_date)
        
        # Create the directory if it doesn't exist
        if not os.path.exists(date_dir):
            os.makedirs(date_dir)
        
        # Create the filename with a timestamp
        timestamp = datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
        filename = os.path.join(date_dir, f"IMG_{timestamp}.jpg")
        
        cv2.imwrite(filename, image)
        print("Row image save")
        
        return filename
    except Exception as e:
        print("save_image_with_timestamp() Exception is : "+ str(e))


def configure_exposure(cam, exposure_value):
    print('*** CONFIGURING EXPOSURE ***\n')

    try:
        result = True

        if cam.ExposureAuto.GetAccessMode() != PySpin.RW:
            print('Unable to disable automatic exposure. Aborting...')
            return False

        cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
        print('Automatic exposure disabled...')

        if cam.ExposureTime.GetAccessMode() != PySpin.RW:
            print('Unable to set exposure time. Aborting...')
            return False

        # Ensure desired exposure time does not exceed the maximum
        exposure_time_to_set = exposure_value
        exposure_time_to_set = min(cam.ExposureTime.GetMax(), exposure_time_to_set)
        cam.ExposureTime.SetValue(exposure_time_to_set)
        print('Shutter time set to %s us...\n' % exposure_time_to_set)

    except PySpin.SpinnakerException as ex:
        print('Error: %s' % ex)
        result = False

    return result

def setFrameGrabbingStartDatetime():
    global configHashMap
    file_path = configHashMap.get(CONFIG_KEY_NAME.FRAME_START_INFO_FILE_PATH)
    try:
        current_time = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        with open(file_path, 'w') as file:
            file.write(f"{current_time}\n")
        
    except Exception as e:
        logger.critical(f"setFrameGrabbingStartDatetime() Exception is : {e}")
        logger.critical(traceback.format_exc())

def acquire_images(cam_list):
    global logger, configHashMap, conveyor_status,conveyorDistance
    client = initMqttClient()
    try:
        result = True
        for i, cam in enumerate(cam_list):
            cam_id = getSerialNumber(cam)
            if cam_id == configHashMap.get(CONFIG_KEY_NAME.TOP_CAMERA_ID) or cam_id == configHashMap.get(CONFIG_KEY_NAME.BOTTOM_CAMERA_ID):

                # Set acquisition mode to continuous
                node_acquisition_mode = PySpin.CEnumerationPtr(cam.GetNodeMap().GetNode('AcquisitionMode'))
                if not PySpin.IsAvailable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
                    print('Unable to set acquisition mode to continuous (node retrieval; camera %d). Aborting... \n' % i)
                    logger.error("Unable to set acquisition mode to continuous - Write")
                    return False

                deviceThroughput=PySpin.CIntegerPtr(cam.GetNodeMap().GetNode('DeviceLinkThroughputLimit'))

                # if device_serial_number in [CAM_1_DEVICE_23263794, CAM_2_DEVICE_22427402, CAM_3_DEVICE_22455027,CAM_4_DEVICE_23022604,CAM_5_DEVICE_23263802,CAM_6_DEVICE_22455025,CAM_7_DEVICE_23029826,CAM_8_DEVICE_22644447]:
                if PySpin.IsAvailable(deviceThroughput) and PySpin.IsReadable(deviceThroughput):
                    device_throughput = 8312000+88000*12 #10512000 #8312000+88000*25 #*2   # Approx. 10.5 MB/s
                    deviceThroughput.SetValue(device_throughput)

                node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
                if not PySpin.IsAvailable(node_acquisition_mode_continuous) or not PySpin.IsReadable(
                        node_acquisition_mode_continuous):
                    print('Unable to set acquisition mode to continuous (entry \'continuous\' retrieval %d). \
                    Aborting... \n' % i)
                    logger.error("Unable to set acquisition mode to continuous - Read")
                    return False

                acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()

                node_acquisition_mode.SetIntValue(acquisition_mode_continuous)

                print('Camera %d acquisition mode set to continuous...' % i)

                # Begin acquiring images
                node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                device_serial_number = node_device_serial_number.GetValue()
                print(f"device_serial_number : {device_serial_number}")
                hours = int(datetime.datetime.now().hour)
                if cam_id == configHashMap.get(CONFIG_KEY_NAME.TOP_CAMERA_ID):
                    if not configure_exposure(cam, 2000.0):
                        logger.error("Unable to set exposure time for Top")
                        return False
                elif cam_id == configHashMap.get(CONFIG_KEY_NAME.BOTTOM_CAMERA_ID):
                    if not configure_exposure(cam, 2000.0):
                        logger.error("Unable to set exposure time for Bottom")
                        return False
                cam.AcquisitionFrameRateAuto = "Off"  # Disables auto frame rate.
                # cam.AcquisitionFrameRateEnable.SetValue(True)
                # cam.AcquisitionFrameRate.SetValue(4)
                cam.AcquisitionFrameRate_set = 20 # Manually sets the frame rate to 20 FPS.

                cam.BeginAcquisition() #Starts acquiring images.
        
        img1=None
        img2=None
        BELT_CYCLE_DURATION = configHashMap.get(CONFIG_KEY_NAME.BELT_CYCLE_DURATION)
        beltDurationInSec =  datetime.timedelta(seconds=BELT_CYCLE_DURATION*BELT_CYCLE_DURATION) 
        lastBeltDurCheckDateTime = datetime.datetime.now()
        SAVE_RAW_IMAGE_FLAG = configHashMap.get(CONFIG_KEY_NAME.SAVE_RAW_IMAGE_FLAG)
        RAW_IMAGE_BOTH = configHashMap.get(CONFIG_KEY_NAME.RAW_IMAGE_BOTH)
        TOP_IMAGE_PATH = configHashMap.get(CONFIG_KEY_NAME.TOP_IMAGE_PATH)
        BOTTOM_IMAGE_PATH = configHashMap.get(CONFIG_KEY_NAME.BOTTOM_IMAGE_PATH)
        # SAVE_RAW_IMAGE_FLAG=1
        while True:
            try:
                for i, cam in enumerate(cam_list):
                    cam_id = getSerialNumber(cam)
                    if cam_id == configHashMap.get(CONFIG_KEY_NAME.TOP_CAMERA_ID) or cam_id == configHashMap.get(CONFIG_KEY_NAME.BOTTOM_CAMERA_ID):
                        grab_start=int(time.time()*1000)
                        node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))

                        if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
                            device_serial_number = node_device_serial_number.GetValue()

                        image_result = cam.GetNextImage(2000) #1000 #  Waits 2 seconds for an image.

                        if image_result.IsIncomplete():
                            # print('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
                            # camlogger.critical('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
                            time.sleep(0.5) #0.1
                            #cam.BeginAcquisition()
                            continue                        
                        else:                            
                            # image_converted = image_result.Convert(PySpin.PixelFormat_BGR8,PySpin.HQ_LINEAR)
                            image_data=image_result.GetNDArray()
                            image_nd=cv2.cvtColor(image_data,cv2.COLOR_BayerRG2RGBA)
                            # Create a unique filename
                            #print(f"grab_time for device {device_serial_number}:" +str(int(time.time()*1000)-grab_start))
                            img1=image_nd
                            image_result.Release()
                            
                            now = datetime.datetime.now()
                            # Format the current date and time
                            TodaysDateTime = now.strftime('%Y_%m_%d_%H_%M_%S_%f')
                            
                            rawImageBothList = os.listdir(RAW_IMAGE_BOTH)
                            if len(rawImageBothList) == 0:
                                lastBeltDurCheckDateTime = datetime.datetime.now()
                                setFrameGrabbingStartDatetime()
                            
                            # Fetch real-time Conveyor distance from MQTT
                            conveyor_distance = f"_DISTANCE_{conveyorDistance}" if conveyorDistance >= 0 else ""
                            if device_serial_number == configHashMap.get(CONFIG_KEY_NAME.BOTTOM_CAMERA_ID):
                                img2=image_nd 
                                if conveyor_status == 1:
                                    if (datetime.datetime.now() - lastBeltDurCheckDateTime) < beltDurationInSec:
                                        filename=RAW_IMAGE_BOTH+f'BOTTOM_{TodaysDateTime}{conveyor_distance}.jpg'
                                        cv2.imwrite(filename, img2)
                                        if os.path.getsize(filename) == 0:
                                            logger.debug(f"Top File  Size Written is Zero")
                                        ##print("Image is Grabbing")
                                    else:
                                        filename=BOTTOM_IMAGE_PATH+'TMP.jpg'
                                        cv2.imwrite(filename, img2)
                                        if os.path.getsize(filename) == 0:
                                            logger.debug(f"Bottom File Size Written is Zero")
                                        #print("Image is Grabbing")
                                    
                                    destFileName = os.path.join(BOTTOM_IMAGE_PATH,"UI/TMP.jpg")
                                    if os.path.exists(destFileName) is False:
                                        shutil.copy2(filename, destFileName)
                                
                                    if SAVE_RAW_IMAGE_FLAG == 1:
                                        current_hour = now.hour
                                        #print("Current Hour:", current_hour)
                                        if current_hour == 14 or current_hour == 15 or current_hour == 16 or current_hour == 17 or current_hour == 18 or current_hour == 19 or current_hour == 20 or current_hour == 21 or current_hour == 22 or current_hour == 23:
                                            save_image_with_timestamp(img2, Marking_Image)
                                else:
                                    destFileName = os.path.join(BOTTOM_IMAGE_PATH,"UI/TMP.jpg")
                                    cv2.imwrite(destFileName, img2)

                            elif device_serial_number == configHashMap.get(CONFIG_KEY_NAME.TOP_CAMERA_ID):
                                img1=image_nd
                                if conveyor_status == 1:
                                    if (datetime.datetime.now() - lastBeltDurCheckDateTime) < beltDurationInSec:
                                        filename=RAW_IMAGE_BOTH+f'TOP_{TodaysDateTime}{conveyor_distance}.jpg'
                                        cv2.imwrite(filename, img1)
                                    else:
                                        filename=TOP_IMAGE_PATH+'TMP.jpg'
                                        cv2.imwrite(filename, img1)
                                
                                    destFileName = os.path.join(TOP_IMAGE_PATH,"UI/TMP.jpg")
                                    if os.path.exists(destFileName) is False:
                                        shutil.copy2(filename, destFileName)
                                
                                    if SAVE_RAW_IMAGE_FLAG == 1:
                                        current_hour = now.hour
                                        #print("Current Hour:", current_hour)
                                        if current_hour == 14 or current_hour == 15 or current_hour == 16 or current_hour == 17 or current_hour == 18 or current_hour == 19 or current_hour == 20 or current_hour == 21 or current_hour == 22 or current_hour == 23:
                                            save_image_with_timestamp(img1, Marking_Image)
                                else:
                                    destFileName = os.path.join(TOP_IMAGE_PATH,"UI/TMP.jpg")
                                    cv2.imwrite(destFileName, img1)
                     
            except PySpin.SpinnakerException as ex:
                logger.critical(f"Inner Loop PySpin.SpinnakerException Error:  {ex}")
                logger.critical(traceback.format_exc())
                result = False
            except Exception as ex:
                logger.critical(f"Inner Loop Exception Error:  {ex}")
                logger.critical(traceback.format_exc())
                result = False

        cam.EndAcquisition()
        cam.DeInit()
        # Clear the camera list and release the system instance
        cam_list.Clear()
           
    except PySpin.SpinnakerException as ex:
        logger.critical(f"PySpin.SpinnakerException Error:  {ex}")
        logger.critical(traceback.format_exc())
        result = False
    except Exception as ex:
        logger.critical('Error Exception : %s' % ex)
        logger.critical(traceback.format_exc())

    return result

def print_device_info(nodemap, cam_num):
    print('Printing device information for camera %d... \n' % cam_num)
    try:
        result = True
        node_device_information = PySpin.CCategoryPtr(nodemap.GetNode('DeviceInformation'))

        if PySpin.IsAvailable(node_device_information) and PySpin.IsReadable(node_device_information):
            features = node_device_information.GetFeatures()
            for feature in features:
                node_feature = PySpin.CValuePtr(feature)
                print('%s: %s' % (node_feature.GetName(),
                                  node_feature.ToString() if PySpin.IsReadable(node_feature) else 'Node not readable'))

        else:
            print('Device control information not available.')
        print()

    except PySpin.SpinnakerException as ex:
        print('Error: %s' % ex)
        return False

    return result

def getSerialNumber(cam):
    device_serial_number = ''
    nodemap_tldevice = cam.GetTLDeviceNodeMap()
    node_device_serial_number = PySpin.CStringPtr(nodemap_tldevice.GetNode('DeviceSerialNumber'))
    if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
        device_serial_number = node_device_serial_number.GetValue()
        # print('Device serial number retrieved as %s...' % device_serial_number)
    return device_serial_number   

def run_multiple_cameras(cam_list):
    result = True
    try:
        device_list = []
        for i, cam in enumerate(cam_list):
            cam_id = getSerialNumber(cam)
            if cam_id == configHashMap.get(CONFIG_KEY_NAME.TOP_CAMERA_ID) or cam_id == configHashMap.get(CONFIG_KEY_NAME.BOTTOM_CAMERA_ID):
                nodemap_tldevice = cam.GetTLDeviceNodeMap()
                device_list.append(getSerialNumber(cam))
                result &= print_device_info(nodemap_tldevice, i)
        
        for i, cam in enumerate(cam_list):
            cam_id = getSerialNumber(cam)
            if cam_id == configHashMap.get(CONFIG_KEY_NAME.TOP_CAMERA_ID) or cam_id == configHashMap.get(CONFIG_KEY_NAME.BOTTOM_CAMERA_ID):
                # Initialize camera
                cam.Init() # starts camera communication.

        # Acquire images on all cameras
        result &= acquire_images(cam_list) # continuously captures and processes images.

        # Once image capture is complete, it deinitializes the cameras.
        for cam in cam_list:
            cam_id = getSerialNumber(cam)
            if cam_id == configHashMap.get(CONFIG_KEY_NAME.TOP_CAMERA_ID) or (cam_id == configHashMap.get(CONFIG_KEY_NAME.BOTTOM_CAMERA_ID)):
                # Deinitialize camera
                cam.DeInit()
    except PySpin.SpinnakerException as e:
        logger.critical("run_multiple_cameras() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
        result = False

    return result

def initCam():
    """
    Initializes the camera system, retrieves the list of available cameras,
    and runs the camera capture process.
    """
    result = True
    try:
        # Retrieve singleton reference to system object
        system = PySpin.System.GetInstance()
    
        # Get current library version
        version = system.GetLibraryVersion()
        print('Library version: %d.%d.%d.%d' % (version.major, version.minor, version.type, version.build))
    
        # Retrieve list of cameras from the system
        cam_list = system.GetCameras()
    
        num_cameras = cam_list.GetSize()
    
        print('Number of cameras detected: %d' % num_cameras)
    
        # Finish if there are no cameras
        if num_cameras == 0:
            
            # Clear camera list before releasing system
            cam_list.Clear()
    
            # Release system instance
            system.ReleaseInstance()
    
            print('Not enough cameras!')
            return False
    
        # Run example on all cameras
        print('Running example for all cameras...')
    
        result = run_multiple_cameras(cam_list)
    
        print('Example complete... \n')
    
        # Clear camera list before releasing system
        cam_list.Clear()
        
        # Release system instance
        system.ReleaseInstance()
    except Exception as e:
        logger.critical("initCam() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())

    return result

def updateProcessID():
    """
    Updates the process ID in the database table PROCESS_ID_TABLE for the FRAME_CAPTURE process.
    """
    db_con = None
    cur = None
    try:
        db_con = getDatabaseConnection()
        cur = db_con.cursor()
        query = f"update PROCESS_ID_TABLE set PROCESS_ID='{FRAME_PROCESS_ID}' where PROCESS_NAME ='FRAME_CAPTURE'"
        cur.execute(query)
        db_con.commit()
    except Exception as e:
        print("updateProcessID() Exception is : "+ str(e))
    finally:
        if cur is not None:
            cur.close()
        if db_con is not None:
            db_con.close()

''' Database Function Start'''
def getDatabaseConnection():
    global logger, configHashMap
    dbConnection = None
    try:
        dbConnection = pymysql.connect(
            host = configHashMap.get(CONFIG_KEY_NAME.DB_HOST),
            user = configHashMap.get(CONFIG_KEY_NAME.DB_USER), 
            passwd = configHashMap.get(CONFIG_KEY_NAME.DB_PASS),
            db = configHashMap.get(CONFIG_KEY_NAME.DB_NAME))
    except Exception as e:
        logger.critical("getDatabaseConnection() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
    return dbConnection

def loadConfiguration():
    global configHashMap
    try:
        print(os.path.curdir)
        config_file_path = os.path.join(os.path.curdir,"config.xml")
        if debugMode is True:
            config_file_path = os.path.join(os.path.curdir,"config_local.xml")
        config_parse = ET.parse(config_file_path)
        config_root = config_parse.getroot()
        
        configHashMap[CONFIG_KEY_NAME.CODE_PATH] = config_root[0][0].text
        configHashMap[CONFIG_KEY_NAME.LOG_FILE_PATH] = config_root[0][1].text
        configHashMap[CONFIG_KEY_NAME.LOG_BACKUP_COUNT] = int(config_root[0][2].text)
        configHashMap[CONFIG_KEY_NAME.RAW_IMAGE_BOTH] = config_root[0][3].text
        configHashMap[CONFIG_KEY_NAME.TOP_IMAGE_PATH] = config_root[0][4].text
        configHashMap[CONFIG_KEY_NAME.BOTTOM_IMAGE_PATH] = config_root[0][5].text
        configHashMap[CONFIG_KEY_NAME.FRAME_START_INFO_FILE_PATH] = config_root[0][6].text
        
        configHashMap[CONFIG_KEY_NAME.DB_USER] = config_root[1][0].text
        configHashMap[CONFIG_KEY_NAME.DB_PASS] = config_root[1][1].text
        configHashMap[CONFIG_KEY_NAME.DB_HOST] = config_root[1][2].text
        configHashMap[CONFIG_KEY_NAME.DB_NAME] = config_root[1][3].text
        
        configHashMap[CONFIG_KEY_NAME.TOP_CAMERA_ID] = config_root[2][0].text
        configHashMap[CONFIG_KEY_NAME.BOTTOM_CAMERA_ID] = config_root[2][1].text

        configHashMap[CONFIG_KEY_NAME.SAVE_RAW_IMAGE_FLAG] = config_root[3][0].text
        configHashMap[CONFIG_KEY_NAME.BELT_CYCLE_DURATION] = int(config_root[3][1].text)

        configHashMap[CONFIG_KEY_NAME.PLC_IP_ADDRESS] = config_root[4][0].text
        configHashMap[CONFIG_KEY_NAME.PLC_WRITE_DB_NUMBER] = int(config_root[4][1].text)
        configHashMap[CONFIG_KEY_NAME.PLC_READ_DB_NUMBER] = int(config_root[4][2].text)

        # Read MQTT details
        configHashMap[CONFIG_KEY_NAME.MQTT_BROKER] = config_root[5][0].text
        configHashMap[CONFIG_KEY_NAME.MQTT_PORT] = int(config_root[5][1].text)
        configHashMap[CONFIG_KEY_NAME.MQTT_TOPIC] = config_root[5][2].text
        
    except Exception as e:
        print(f"loadConfiguration() Exception is {e}")
        print(traceback.format_exc()) 

def initializeLogger():
    global logger, configHashMap
    try:
        ''' Initializing Logger '''
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        
        # Define the log file format
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Create a TimedRotatingFileHandler for daily rotation
        log_file = configHashMap.get(CONFIG_KEY_NAME.LOG_FILE_PATH)+os.path.basename(__file__[:-2])+"log"
        file_handler = TimedRotatingFileHandler(log_file, when='midnight', backupCount=configHashMap.get(CONFIG_KEY_NAME.LOG_BACKUP_COUNT))
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.debug("Frame capture logger Initialized")
    except Exception as e:
        print(f"initializeLogger() Exception is {e}")
        print(traceback.format_exc())


def on_message(client, userdata, message):
    """Handles incoming MQTT messages and updates defectDistance."""
    global conveyorDistance
    try:
        data = json.loads(message.payload.decode().strip())
        distance_value = data.get("distance")

        if isinstance(distance_value, (int, float)) and distance_value > 0:
            conveyorDistance = distance_value
            logging.debug(f"Distance updated: {conveyorDistance} meters")
        else:
            logging.warning("Invalid distance received")

    except json.JSONDecodeError:
        logging.error("Error decoding JSON")

def initMqttClient():
    """Initializes and starts the MQTT client."""
    global configHashMap
    client = mqtt.Client()
    client.on_message = on_message

    try:
        client.connect(configHashMap.get(CONFIG_KEY_NAME.MQTT_BROKER), configHashMap.get(CONFIG_KEY_NAME.MQTT_PORT), 60)
        logging.info("MQTT Connected")
        client.subscribe(configHashMap.get(CONFIG_KEY_NAME.MQTT_TOPIC))
        client.loop_start()
        return client
    except Exception as e:
        logging.error(f"MQTT Connection Error: {e}")
        return None

if __name__ == '__main__':
    timer_st = RepeatedTimer(1 * 5, take_conveyor_status) # # Repeatedly check conveyor status every 5 seconds
    loadConfiguration()
    initializeLogger()
    updateProcessID()
    while True:
        try:
            initCam()
            time.sleep(10)
        except:
            logger.error("Error in main function")
            time.sleep(10)
