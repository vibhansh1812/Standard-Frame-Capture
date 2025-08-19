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

# from IMG_CHECK import check_black_images

debugMode = False

''' UI Process ID and Base Code Path '''
FC_ONE_PROCESS_ID = os.getpid()
BASE_PATH = "C:/Users/Admin/Insightzz/PRODUCTION_CODE/FRAMECAPTURE"#os.getcwd()
logger = None
configHashMap = {}
FC_ONE_CODE_PATH = BASE_PATH+"/"

SIDE6_DEVICE = "23494178" 
SIDE9_DEVICE = "23475115" 
SIDE12_DEVICE = "23475102" 
SIDE13_DEVICE = "23475123" 
SIDE14_DEVICE = "23475111" 
SIDE15_DEVICE = "23473377" 


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
        config_file_path = os.path.join(BASE_PATH,"config_two.xml")
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
        logger.debug("FA FC TWO Module Initialized")
    except Exception as e:
        print(f"initializeLogger() Exception is {e}")
        print(traceback.format_exc())
        
def updatetrigger(process,complete):
    dbConnection = None
    cur = None
    try:
        dbConnection =getDatabaseConnection()
        cur = dbConnection.cursor()
        query = f"UPDATE FRAME_CAPTURE_STATUS_TABLE SET framecapturetwocomplete='{complete}' WHERE ID = '2';"
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

def update_Camera1_health_status(STATUS):
    dbConnection = None
    cur = None
    try:
        dbConnection = getDatabaseConnection()
        cur = dbConnection.cursor() 
        query = f"update HEALTH_STATUS_TABLE set SYSTEM_STATUS = '{STATUS}' where SYSTEM_NAME = 'CAMERA_2'"
        cur.execute(query)
        dbConnection.commit()
    except Exception as e:
        logger.critical("update_Camera1_health_status() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
    finally:
        if cur is not None:
            cur.close()
        if dbConnection is not None:
            dbConnection.close()

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
            #logger.critical(f"Exposure et Properly for Camera ID : {device_id}")
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
            for i, cam in enumerate(cam_list):
                try:
                   
                    camNodeMap=cam.GetNodeMap()
                    
                    node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                    device_serial_number = node_device_serial_number.GetValue()
                    if device_serial_number in [SIDE6_DEVICE,SIDE9_DEVICE,SIDE12_DEVICE,SIDE13_DEVICE,SIDE14_DEVICE,SIDE15_DEVICE]:
                        current_cam.append(cam)
                        
                        deviceThroughput=PySpin.CIntegerPtr(cam.GetNodeMap().GetNode('DeviceLinkThroughputLimit'))
                        if PySpin.IsAvailable(deviceThroughput) and PySpin.IsReadable(deviceThroughput) and PySpin.IsWritable(deviceThroughput):
                            device_throughput=int(10000000)
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
    
    def capture_dummy_images(self, cam_list, device_list):
        # print(device_list, "---------------------------------------------")

        try:
            vin_number = "DUMMY_IMAGES"
            currDateTime = datetime.datetime.now()
            hour = int(currDateTime.hour)
            minute = int(currDateTime.minute)

            if hour == 6 and minute > 0 and minute < 25:
                for counter in range(0, 20):
                    current_cam=self.configuration_camera(device_list)
                    
                    captureImgList, fl_list = self.acquire_images(current_cam,vin_number)
                    logger.debug(f"Frame Capture Status First Run for VIN : {vin_number} is {captureImgList} ")
                    time.sleep(0.05)
                        
                for i, cam in enumerate(cam_list):
                    node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                    device_serial_number = node_device_serial_number.GetValue()
                    if device_serial_number in [SIDE6_DEVICE,SIDE9_DEVICE,SIDE12_DEVICE,SIDE13_DEVICE,SIDE14_DEVICE,SIDE15_DEVICE]:
                        device_list.append(cam)
                
                for i, cam in enumerate(device_list): 
                    cam.Init()
            # else:
            #     print(f"Dummy Image Capture is Out of Given Time Period ")
                
        except Exception as e:
            logger.critical("DummyFrameCapture() Exception is : "+ str(e))
            logger.critical(traceback.format_exc())

    def acquire_images(self,cam_list,vin_number):
        capturedImageList = [False,False,False,False,False]
        fileName_list = []
        try:
            image_incomplete_counter = 0
            counter = 0
            processor = PySpin.ImageProcessor()
            processor.SetColorProcessing(PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR)
            complete_capture=False
            engine_number=vin_number
            # print("VIN NUMBER AND MDOEL IS ------------------------------------",engine_number)
            SAVE_IMG_FILE_PATH=os.path.join(configHashMap.get(CONFIG_KEY_NAME.RAW_IMAGE_PATH),engine_number)
           
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
                            time.sleep(0.2)
                            #print("device_serial_number is :",device_serial_number)      
                            try:
                                image_result = cam.GetNextImage(2000)
                            except Exception as e:
                                print(f"Frame read exception is : {e}")
                                continue
                            
                            if image_result.IsIncomplete():
                                image_incomplete_counter = image_incomplete_counter + 1
                                print(device_serial_number)
                                print('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
                                print(traceback.format_exc())
                                logger.error(traceback.format_exc())
                                logger.error('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
                            else:
                                #print("enter in condition")
                                complete_capture=True
                                image_incomplete_counter = 0                                    
                            
                                image_converted = processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                                counter = counter + 1
                                current_time=time.time()
                                if device_serial_number == SIDE6_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_6.jpeg"                                
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)     
                                    fileName_list.append(img)  
                                    image_result.Release()
                                    capturedImageList[0] = True
                                    logger.debug(f"engine_number is {engine_number} device_serial_number{device_serial_number} image save fileName is : {fileName}")
                                    print("fileName is===================:",fileName)

                                if device_serial_number == SIDE9_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_9.jpeg"                             
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)      
                                    fileName_list.append(img)  
                                    image_result.Release()
                                    capturedImageList[1] = True
                                    logger.debug(f"engine_number is {engine_number} device_serial_number{device_serial_number} image save fileName is : {fileName}")
                                    print("fileName is===================:",fileName)
                                
                                if device_serial_number == SIDE12_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_12.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)    
                                    fileName_list.append(img)    
                                    image_result.Release()
                                    capturedImageList[2] = True
                                    logger.debug(f"engine_number is {engine_number} device_serial_number{device_serial_number} image save fileName is : {fileName}")
                                    print("fileName is===================:",fileName)

                                if device_serial_number == SIDE13_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_13.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img)      
                                    fileName_list.append(img)  
                                    image_result.Release()
                                    capturedImageList[2] = True
                                    logger.debug(f"engine_number is {engine_number} device_serial_number{device_serial_number} image save fileName is : {fileName}")
                                    print("fileName is===================:",fileName)
                                if device_serial_number == SIDE14_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_14.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img) 
                                    fileName_list.append(img)  
                                    image_result.Release()
                                    capturedImageList[3] = True
                                    logger.debug(f"engine_number is {engine_number} device_serial_number{device_serial_number} image save fileName is : {fileName}")
                                    print("fileName is===================:",fileName)
                                if device_serial_number == SIDE15_DEVICE:
                                    fileName = f"{SAVE_IMG_FILE_PATH}/IMG_15.jpeg"
                                    img = image_converted.GetNDArray()
                                    cv2.imwrite(fileName, img) 
                                    fileName_list.append(img)  
                                    image_result.Release()
                                    capturedImageList[4] = True
                                    logger.debug(f"engine_number is {engine_number} device_serial_number{device_serial_number} image save fileName is : {fileName}")
                                    print("fileName is===================:",fileName)
                                update_Camera1_health_status("ACTIVE")
            except PySpin.SpinnakerException as ex:
                update_Camera1_health_status("INACTIVE")
                print('Error: %s' % ex)
                logger.debug(f"Error engine_number is {engine_number} device_serial_number {device_serial_number} ex IS {ex} ")
                result = False

        except PySpin.SpinnakerException as ex:
            update_Camera1_health_status("INACTIVE")
            print(device_serial_number)
            print(traceback.format_exc)
            print(f"Exception in {ex}")
            logger.error(f"Error {device_serial_number} CAM is not connected AND ex IS {ex}")
            logger.error('Error: %s' % ex)
            result = False

        return capturedImageList, fileName_list

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
            capture=False
            device_list=[]
            system = PySpin.System.GetInstance()
            version = system.GetLibraryVersion()
            capture=False
            device_list=[]
            cam_list = system.GetCameras()
            num_cameras = cam_list.GetSize()
            inital=False
            for i, cam in enumerate(cam_list):
                    node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                    device_serial_number = node_device_serial_number.GetValue()
                    if device_serial_number in [SIDE6_DEVICE,SIDE9_DEVICE,SIDE12_DEVICE,SIDE13_DEVICE,SIDE14_DEVICE,SIDE15_DEVICE]:
                        print(device_serial_number)
                        device_list.append(cam)

            for i, cam in enumerate(device_list):
                time.sleep(0.1)
                cam.Init()

            # print(device_list, "=================")
            self.capture_dummy_images(cam_list, device_list)
                    
            vin_number="EMPTY"
            vin_model=""
            previousenginenumber=""
            logger.debug(f"start init fun ")
            isFirstRun = False
            update_Camera1_health_status("ACTIVE")
            while True:
                try:

                    self.capture_dummy_images(cam_list, device_list)

                    start,vin_number,framecaptureonecomplete=fetchtrigger()
                    if start==1 and framecaptureonecomplete ==1 :
                        if vin_number!=previousenginenumber:#and capture==False:  
                            time.sleep(1)             
                            if device_list is not None:
                                starttime=time.time()*1000 
                                previousenginenumber=vin_number
                                print("2nd camera frame capture ========================= start")
                                current_cam=self.configuration_camera(device_list)
                                runCount = 0
                                # blackCount = 0
                                # black_status = True
                                if isFirstRun is True:
                                    while True:
                                        captureImgList, file_name_list = self.acquire_images(current_cam,vin_number)

                                        t1 = datetime.datetime.now()
                                        # for i in file_name_list: 
                                        #     black_status = check_black_images(i)
                                        #     if black_status: 
                                        #         logger.debug(f"Frame Captured black Image for {i} ")
                                        #         blackCount += 1
                                        #         break

                                        # file_name_list.clear()

                                        # if blackCount > 50: 
                                        #     logger.debug(f"Frame Captured black Image but was taken out of loop ")
                                        #     black_status = False
                                        # if black_status: continue

                                        logger.debug(f"time taken for checking black images: {(datetime.datetime.now() - t1).total_seconds()} ")
                                        logger.debug(f"Frame Capture Status First Run for VIN : {vin_number} is {captureImgList} ")
                                        runCount = runCount + 1
                                        time.sleep(0.5)
                                        if runCount >=5: # and not black_status
                                            break
                                else:
                                    runCount = 0
                                    # blackCount = 0
                                    # black_status = True
                                    while True:
                                        
                                        captureImgList, file_name_list = self.acquire_images(current_cam,vin_number)
                                        
                                        t1 = datetime.datetime.now()

                                        logger.debug(f"time taken for checking black images: {(datetime.datetime.now() - t1).total_seconds()} ")
                                        logger.debug(f"Frame Capture Status for VIN : {vin_number} is {captureImgList} ")
                                        if captureImgList.count(True) != 5:
                                            runCount = runCount + 1
                                            # time.sleep(1)
                                            if runCount >=3: # and not black_status
                                                break
                                            continue

                                        break
                                
                                isFirstRun = False 
                                logger.debug(f"acquire_images fun done for vin_number is {vin_number}")
                                updatetrigger(process=0,complete=1)
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
                                    try:
                                        cam.EndAcquisition()
                                        time.sleep(0.5)
                                        cam.DeInit()
                                    except Exception as e:
                                        print(e)
                                device_list=[]
                                inital=False
                                capture=True

                    else:
                        if start==0:
                            capture=False
                            if inital==False and len(device_list) ==0:
                                for i, cam in enumerate(cam_list):
                                    node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                                    device_serial_number = node_device_serial_number.GetValue()
                                    if device_serial_number in[SIDE6_DEVICE,SIDE9_DEVICE,SIDE12_DEVICE,SIDE13_DEVICE,SIDE14_DEVICE,SIDE15_DEVICE]:
                                        device_list.append(cam)
                                for i, cam in enumerate(device_list):
                                    time.sleep(0.1) 
                                    cam.Init()
                                    
                        
                                    
                except Exception as e:
                    print(e)
        except Exception as e:
            print(e)  

def fetchtrigger():
    dbConnection = None
    cur = None
    processone= 0
    ENGINE_NUMBER = ""
    framecaptureonecomplete = 0
    try:
        dbConnection =getDatabaseConnection()
        cur = dbConnection.cursor()
        query = f"SELECT framecapture,ENGINE_NUMBER,framecaptureonecomplete FROM FRAME_CAPTURE_STATUS_TABLE;"
        cur.execute(query)
        data=cur.fetchone()
        processone=data[0]
        ENGINE_NUMBER=data[1]
        framecaptureonecomplete = data[2]
    except Exception as e:
        logger.critical("fetchtrigger() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
    finally:
        if cur is not None:
            cur.close()
        if dbConnection is not None:
            dbConnection.close()
    return processone,ENGINE_NUMBER,framecaptureonecomplete


def mainFunction():
    ImageCapture()
    
if "__main__"==__name__:
    loadConfiguration()
    initializeLogger()
    mainFunction()
