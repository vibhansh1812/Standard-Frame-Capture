#!/usr/bin/python3
import os
import PySpin
import time 
import cv2
import pymysql
import ast
import xml.etree.ElementTree as ET
import pypyodbc as odbc
import logging
import traceback
from logging import handlers
from logging.handlers import TimedRotatingFileHandler
import datetime
import threading
import shutil
import datetime

debugMode = False

''' UI Process ID and Base Code Path '''
FC_ONE_PROCESS_ID = os.getpid()
BASE_PATH = "C:/Users/Admin/Insightzz/PRODUCTION_CODE/FRAMECAPTURE"#os.getcwd()
logger = None
configHashMap = {}
FC_ONE_CODE_PATH = BASE_PATH+"/"

SIDE1_DEVICE = "23475124"
SIDE2_DEVICE = "23475121"
SIDE3_DEVICE = "23475112"
SIDE4_DEVICE = "23475117"
SIDE5_DEVICE = "23475100"

plclock=threading.Lock()

WAIT_TIME = 0.0001 #in seconds - this limits polling time and should be less than the frame rate period 
GAIN_VALUE = 10 #in dB, 0-40;
GAMMA_VALUE = 0.4 #0.25-1
FRAMES_PER_SECOND = 1 #this is determined by triggers sent from behavior controller
FRAMES_TO_RECORD = 400*FRAMES_PER_SECOND #frame rate * num seconds to record; this should match # expected exposure triggers from DAQ counter output
CAM_TIMEOUT = 1000 #in ms; time to wait for another image before aborting

class CONFIG_KEY_NAME:
    CODE_PATH = "CODE_PATH"
    LOG_FILE_PATH = "LOG_FILE_PATH"
    LOG_BACKUP_COUNT = "LOG_BACKUP_COUNT"
    RAW_IMAGE_PATH = "RAW_IMAGE_PATH"
    INF_IMAGE_PATH = "INF_IMAGE_PATH"
    UI_TRIGGER_FILE_PATH = "UI_TRIGGER_FILE_PATH"
    TRIGGER_FILE_PATH = "TRIGGER_FILE_PATH"
    
    DRIVER_NAME = "DRIVER_NAME"
    SERVER_NAME = "SERVER_NAME"
    CONNECTION_TYPE = "CONNECTION_TYPE"
    DB_NAME = "DB_NAME"

def loadConfiguration():
    global configHashMap
    try:
        print(BASE_PATH)
        config_file_path = os.path.join(BASE_PATH,"config_one.xml")
        if debugMode is True:
            config_file_path = os.path.join(BASE_PATH,"config_local.xml")
        config_parse = ET.parse(config_file_path)
        config_root = config_parse.getroot()
        
        configHashMap[CONFIG_KEY_NAME.CODE_PATH] = config_root[0][0].text
        configHashMap[CONFIG_KEY_NAME.LOG_FILE_PATH] = config_root[0][1].text
        configHashMap[CONFIG_KEY_NAME.LOG_BACKUP_COUNT] = int(config_root[0][2].text)
        configHashMap[CONFIG_KEY_NAME.RAW_IMAGE_PATH] = config_root[0][3].text
        configHashMap[CONFIG_KEY_NAME.INF_IMAGE_PATH] = config_root[0][4].text
        configHashMap[CONFIG_KEY_NAME.UI_TRIGGER_FILE_PATH] = config_root[0][5].text
        configHashMap[CONFIG_KEY_NAME.TRIGGER_FILE_PATH] = config_root[0][6].text
        
        configHashMap[CONFIG_KEY_NAME.DRIVER_NAME] = config_root[1][0].text
        configHashMap[CONFIG_KEY_NAME.SERVER_NAME] = config_root[1][1].text
        configHashMap[CONFIG_KEY_NAME.CONNECTION_TYPE] = int(config_root[1][2].text)
        configHashMap[CONFIG_KEY_NAME.DB_NAME] = config_root[1][3].text
        
    except Exception as e:
        print(f"loadConfiguration() Exception is {e}")
        print(traceback.format_exc()) 

''' Database Function Start'''
def getDatabaseConnection():
    global configHashMap
    dbConnection = None
    try:
        DRIVER_NAME = configHashMap.get(CONFIG_KEY_NAME.DRIVER_NAME)
        SERVER_NAME = configHashMap.get(CONFIG_KEY_NAME.SERVER_NAME)
        DATABASE_NAME = configHashMap.get(CONFIG_KEY_NAME.DB_NAME)
        connection_string = f"""
            DRIVER={{{DRIVER_NAME}}};
            SERVER={{{SERVER_NAME}}};
            DATABASE={{{DATABASE_NAME}}};
            trustServerCertificate=true;
            """
        dbConnection = odbc.connect(connection_string)

    except Exception as e:
        logger.critical("getDatabaseConnection() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
    return dbConnection

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
        logger.debug("FA FC ONE Module Initialized")
    except Exception as e:
        print(f"initializeLogger() Exception is {e}")
        print(traceback.format_exc())

def configure_exposure(camera, exposure_value):
    print('*** CONFIGURING EXPOSURE ***\n')

    try:
        result = True
        if camera.ExposureAuto.GetAccessMode() != PySpin.RW:
            print('Unable to disable automatic exposure. Aborting...')
            return False

        camera.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
        print('Automatic exposure disabled...')

        if camera.ExposureTime.GetAccessMode() != PySpin.RW:
            print('Unable to set exposure time. Aborting...')
            return False

        # Ensure desired exposure time does not exceed the maximum
        exposure_time_to_set = exposure_value
        exposure_time_to_set = min(camera.ExposureTime.GetMax(), exposure_time_to_set)
        camera.ExposureTime.SetValue(exposure_time_to_set)
        print('Shutter time set to %s us...\n' % exposure_time_to_set)

    except PySpin.SpinnakerException as ex:
        print('Error: %s' % ex)
        result = False

class ImageCapture():
    Frame=None
    stopThread=False

    def __init__(self):
        self.data_collection=False
        try:
            t1=threading.Thread(target=self.initCam)
            t1.start()
        except Exception as e:
            logger.error(traceback.format_exc())
            
    def configure_exposure(self,cam, exposure_value, device_id):
        try:
            result = True
            if cam.ExposureAuto.GetAccessMode() != PySpin.RW:
                return False

            cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)

            if cam.ExposureTime.GetAccessMode() != PySpin.RW:
                return False

            exposure_time_to_set = exposure_value
            # exposure_time_to_set = min(cam.ExposureTime.GetMax(), exposure_time_to_set)
            cam.ExposureTime.SetValue(exposure_time_to_set)
            logger.critical(f"Exposure et Properly for Camera ID : {device_id}")
        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            logger.error(traceback.format_exc())
            logger('Error: %s' % ex)
            result = False
        return result
    
    def configuration_camera(self,cam_list):
        try:
            current_cam=[]
            result = True
            # time.sleep(2.1)
            for i, cam in enumerate(cam_list):
                try:
                    # time.sleep(1)
                    # tlStreamSetup=cam.GetTLStreamNodeMap()
                    camNodeMap=cam.GetNodeMap()
                    
                    node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                    device_serial_number = node_device_serial_number.GetValue()
                    if device_serial_number in [SIDE1_DEVICE,SIDE2_DEVICE,SIDE3_DEVICE,SIDE4_DEVICE,SIDE5_DEVICE]:
                        current_cam.append(cam)
                        # time.sleep(2)
                        # resendFramesNode=PySpin.CBooleanPtr(tlStreamSetup.GetNode("StreamPacketResendEnable"))
                        
                        
                        deviceThroughput=PySpin.CIntegerPtr(cam.GetNodeMap().GetNode('DeviceLinkThroughputLimit'))
                        if PySpin.IsAvailable(deviceThroughput) and PySpin.IsReadable(deviceThroughput) and PySpin.IsWritable(deviceThroughput):
                            device_throughput=int(6000000)
                            if device_throughput>int(deviceThroughput.GetMax()):
                                device_throughput=int(deviceThroughput.GetMax())
                            elif device_throughput<int(deviceThroughput.GetMin()):
                                device_throughput=int(deviceThroughput.GetMin())
                                
                            device_throughput = max(int(deviceThroughput.GetMin()), device_throughput)
                            #check value
                            incrementVal=int(deviceThroughput.GetInc())
                            properval=int((device_throughput-int(deviceThroughput.GetMin()))%incrementVal)
                            if properval==0:
                                deviceThroughput.SetValue(device_throughput)
                            else:
                                nearestInt=int((device_throughput-int(deviceThroughput.GetMin()))/incrementVal)
                                ndevice_throughput=int(int(deviceThroughput.GetMin())+((nearestInt-1)*incrementVal))
                                logger.critical(f"Changing throughput value: oldval{device_throughput} to newval:{ndevice_throughput}.")
                        # ExposureTime=PySpin.CFloatPtr(camNodeMap.GetNode("ExposureTime"))
                        # requiredExposureVal=float(55000)
                        # self.configure_exposure(cam, requiredExposureVal, device_serial_number)
                        # if PySpin.IsAvailable(ExposureTime) and PySpin.IsReadable(ExposureTime) and PySpin.IsWritable(ExposureTime):
                        #     requiredExposureVal=float(14000)
                        #     if requiredExposureVal>=ExposureTime.GetMin() and requiredExposureVal<=ExposureTime.GetMax():
                        #         ExposureTime.SetValue(requiredExposureVal)
                        #     else:
                        #         logger.critical("Incorrect exposure in config- setting to min value.")
                        #         ExposureTime.SetValue(ExposureTime.GetMin())

                       
                        cam.BeginAcquisition()
                            
                except Exception as e:
                    print(f"{e}------{device_serial_number}")
                    print(e)
                    continue
        except Exception as e:
            print(e)
        return current_cam

    def acquire_images(self,cam_list,vin_number):
        capturedImageList = [False,False,False,False,False]
        try:
            image_incomplete_counter = 0
            counter = 0
            processor = PySpin.ImageProcessor()
            processor.SetColorProcessing(PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR)
            complete_capture=False
            engine_number=vin_number
            print("VIN NUMBER AND MDOEL IS ------------------------------------",engine_number)
            # SAVE_IMG_FILE_PATH=f"{PARENT_PATH}{engine_number}"#os.path.join(PARENT_PATH,TodaysDate)
            SAVE_IMG_FILE_PATH=os.path.join(configHashMap.get(CONFIG_KEY_NAME.RAW_IMAGE_PATH),engine_number)
            if not os.path.exists(SAVE_IMG_FILE_PATH):
                os.makedirs(SAVE_IMG_FILE_PATH)
           
            try:
                TodaysDate = datetime.datetime.now().strftime('%Y_%m_%d') 
                if image_incomplete_counter >= 10:
                    self.initCam()
                    image_incomplete_counter = 0
                else:
                    for i, cam in enumerate(cam_list):
                        grab_start = int(time.time() * 1000)
                        node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                        if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
                            device_serial_number = node_device_serial_number.GetValue()
                            #time.sleep(0.1)
                            
                            image_result = None
                            try:
                                image_result = cam.GetNextImage(2000)
                            except Exception as e:
                                 print('Error: %s' % e)
                                 continue
                            if image_result.IsIncomplete():
                                image_incomplete_counter = image_incomplete_counter + 1
                                print(device_serial_number)
                                print('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
                                print(traceback.format_exc())
                                logger.error(traceback.format_exc())
                                logger.error('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
                            else:
                                complete_capture=True
                                image_incomplete_counter = 0                                    
                            
                                image_converted = processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                                counter = counter + 1
                                current_time=time.time()
                                if device_serial_number == SIDE1_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_1.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)
                                    image_result.Release()
                                    capturedImageList[0] = True
                                if device_serial_number == SIDE2_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_2.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)
                                    image_result.Release()
                                    capturedImageList[1] = True
                                    # time.sleep(1)
                                if device_serial_number == SIDE3_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_3.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)
                                    image_result.Release()
                                    capturedImageList[2] = True
                                if device_serial_number == SIDE4_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_4.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)
                                    image_result.Release()
                                    capturedImageList[3] = True
                                if device_serial_number == SIDE5_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_5.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)
                                    image_result.Release()
                                    capturedImageList[4] = True
                                
            except PySpin.SpinnakerException as ex:
                print('Error: %s' % ex)
                result = False          

        except PySpin.SpinnakerException as ex:
            print(device_serial_number)
            print(traceback.format_exc)
            print(f"Exception in {ex}")
            logger.error(f"{device_serial_number} CAM is not connected")
            logger.error('Error: %s' % ex)
            result = False

        return capturedImageList

    def print_device_info(self,nodemap, cam_num):
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
                logger.error(traceback.format_exc())

        except PySpin.SpinnakerException as ex:
            logger.error(traceback.format_exc())
            return False

        return result

    def getSerialNumber(self,cam):
        device_serial_number = ''
        nodemap_tldevice = cam.GetTLDeviceNodeMap()
        node_device_serial_number = PySpin.CStringPtr(nodemap_tldevice.GetNode('DeviceSerialNumber'))
        if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
            device_serial_number = node_device_serial_number.GetValue()
        return device_serial_number   

    def initCam(self):
        try:
            result = True
            system = PySpin.System.GetInstance()
            version = system.GetLibraryVersion()
            device_list=[]
            system = PySpin.System.GetInstance()
            version = system.GetLibraryVersion()
            
            device_list=[]
            cam_list = system.GetCameras()
            num_cameras = cam_list.GetSize()
            inital=False
            for i, cam in enumerate(cam_list):
                    node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                    device_serial_number = node_device_serial_number.GetValue()
                    if device_serial_number in [SIDE1_DEVICE,SIDE2_DEVICE,SIDE3_DEVICE,SIDE4_DEVICE,SIDE5_DEVICE]:
                        print(device_serial_number)
                        device_list.append(cam)

            for i, cam in enumerate(device_list):
                    node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                    device_serial_number = node_device_serial_number.GetValue()
                    print(f"Cam init {device_serial_number}")
                    cam.Init()
                    
            vin_number="EMPTY"
            capture=False
            previousvinnumber=""
            isFirstRun = True
            while True:
                try:
                    time.sleep(0.2)
                    start,vin_number=fetchtrigger()
                    if start==1 and vin_number != "EMPTY" and vin_number != "DUMMY":
                        logger.debug(f"Starting Frame Capture VIN Number : {vin_number} at {datetime.datetime.now()} ")
                        if vin_number!=previousvinnumber:
                            if device_list is not None:
                                starttime=time.time()*1000
                                #previousvinnumber=vin_number
                                runCount = 0
                                current_cam=self.configuration_camera(device_list)
                                if isFirstRun is True:
                                    while True:
                                        captureImgList = self.acquire_images(current_cam,vin_number)
                                        logger.debug(f"Frame Capture Status First Run for VIN : {vin_number} is {captureImgList} ")
                                        runCount = runCount + 1
                                        # time.sleep(0.1)
                                        if runCount >=20:
                                            break
                                else:
                                    runCount = 0
                                    while True:
                                        captureImgList = self.acquire_images(current_cam,vin_number)
                                        logger.debug(f"Frame Capture Status for VIN : {vin_number} is {captureImgList} ")
                                        if captureImgList.count(True) != 5:
                                            runCount = runCount + 1
                                            # time.sleep(0.2)
                                            if runCount >=1:
                                                break
                                            continue
                                        break
                                
                                isFirstRun = False
                                updatetrigger(process=0,complete=1)
                                previousvinnumber=vin_number
                                logger.debug(f"acquire_images fun done for vin_number is {vin_number}")
                                endtime=time.time()*1000
                                
                                if os.path.exists(configHashMap.get(CONFIG_KEY_NAME.UI_TRIGGER_FILE_PATH)):
                                    os.remove(configHashMap.get(CONFIG_KEY_NAME.UI_TRIGGER_FILE_PATH))
                                    with open(configHashMap.get(CONFIG_KEY_NAME.UI_TRIGGER_FILE_PATH), "w") as trigger_file:
                                        trigger_file.write(vin_number)
                                try:
                                    if os.path.exists(configHashMap.get(CONFIG_KEY_NAME.TRIGGER_FILE_PATH)):
                                        os.remove(configHashMap.get(CONFIG_KEY_NAME.TRIGGER_FILE_PATH))
                                        with open(configHashMap.get(CONFIG_KEY_NAME.TRIGGER_FILE_PATH), "w") as trigger_file:
                                            trigger_file.write(vin_number)
                                    else:
                                        with open(configHashMap.get(CONFIG_KEY_NAME.TRIGGER_FILE_PATH), "w") as trigger_file:
                                            trigger_file.write(vin_number)
                                except Exception as e:
                                    print(e)
                                for cam in device_list:
                                    # for cam in cam_list:
                                        try:
                                            cam.EndAcquisition()  # Example method to stop streaming
                                            time.sleep(0.2)
                                            cam.DeInit()
                                        except Exception as e:
                                            print(e)
                                device_list=[]
                                inital=False
                                capture=True
                        else:
                            logger.debug(f"Previous and Current Engine Number is same : Previous : {previousvinnumber} , Current : {vin_number}, Capture Flag is {capture}")
                            if capture is False:
                                time.sleep(0.5)
                                updateAllTriggerStatus() 
                    else:
                        if start==0:
                            capture=False
                            # plclock.acquire()
                            # plcobj.write_bit(1,0)
                            # plclock.release()
                            # time.sleep(0.5)
                            if inital==False and len(device_list) ==0:
                                for i, cam in enumerate(cam_list):
                                    node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                                    device_serial_number = node_device_serial_number.GetValue()
                                    if device_serial_number in [SIDE1_DEVICE,SIDE2_DEVICE,SIDE3_DEVICE,SIDE4_DEVICE,SIDE5_DEVICE]:
                                        device_list.append(cam)
                                for i, cam in enumerate(device_list): 
                                    cam.Init()
                                
                                    
                except Exception as e:
                    print(e)
        except Exception as e:
            print(e) 
            
def updatetrigger(process,complete):
    dbConnection = None
    cur = None
    try:
        dbConnection =getDatabaseConnection()
        cur = dbConnection.cursor()
        query = f"UPDATE FRAME_CAPTURE_STATUS_TABLE SET framecaptureonecomplete='{complete}', framecapturetwocomplete='{complete}' WHERE ID = '1';"
        cur.execute(query)
        dbConnection.commit()
    except Exception as e:
        logger.critical("updatetrigger() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
    finally:
        if cur is not None:
            cur.close()
        if dbConnection is not None:
            dbConnection.close() 

def updateAllTriggerStatus():
    dbConnection = None
    cur = None
    try:
        dbConnection =getDatabaseConnection()
        cur = dbConnection.cursor()
        query = f"UPDATE FRAME_CAPTURE_STATUS_TABLE SET framecaptureonecomplete='{1}', framecapturetwocomplete='{1}', INFERENCE_STATUS = '{1}' WHERE ID = '1';"
        cur.execute(query)
        dbConnection.commit()
    except Exception as e:
        logger.critical("updatetrigger() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
    finally:
        if cur is not None:
            cur.close()
        if dbConnection is not None:
            dbConnection.close() 

def fetchtrigger():
    dbConnection = None
    cur = None
    processone= 0
    ENGINE_NUMBER = ""
    try:
        dbConnection =getDatabaseConnection()
        cur = dbConnection.cursor()
        query = f"SELECT framecapture, ENGINE_NUMBER FROM FRAME_CAPTURE_STATUS_TABLE;"
        cur.execute(query)
        data=cur.fetchone()
        processone=data[0]
        ENGINE_NUMBER=data[1]
    except Exception as e:
        logger.critical("fetchtrigger() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
    finally:
        if cur is not None:
            cur.close()
        if dbConnection is not None:
            dbConnection.close()
    return processone,ENGINE_NUMBER
       
def mainFunction():
    ImageCapture()
    
if "__main__"==__name__:
    loadConfiguration()
    initializeLogger()
    mainFunction()
