import cv2
import datetime
import gc
import logging
import os
import PySpin
import pypyodbc as odbc
import shutil
import time 
import traceback
import threading
import xml.etree.ElementTree as ET

from logging import handlers
from logging.handlers import TimedRotatingFileHandler
# from IMG_CHECK import check_black_images

''' UI Process ID and Base Code Path '''
FC_ONE_PROCESS_ID = os.getpid()
BASE_PATH = "C:/Users/Admin/Insightzz/PRODUCTION_CODE/FRAMECAPTURE"#os.getcwd()
logger = None
configHashMap = {}
FC_ONE_CODE_PATH = BASE_PATH + "/"

SIDE1_DEVICE = "23475099"
SIDE2_DEVICE = "23475110" 
SIDE3_DEVICE = "23473372"
SIDE4_DEVICE = "23475127"
SIDE5_DEVICE = "23473376" 
SIDE6_DEVICE = "23473373"
SIDE7_DEVICE = "23473380"
# SIDE8_DEVICE = "23475103"
SIDE9_DEVICE = "23475095"
SIDE10_DEVICE = "23475126"
SIDE11_DEVICE = "23475104"
SIDE12_DEVICE = "23494174"
# SIDE13_DEVICE = "23475131"
SIDE14_DEVICE = "23475128" 
SIDE16_DEVICE = "23475114"

DEVICE_NUM = {
    "23475099":1,
    "23475110":2,
    "23473372":3,
    "23475127":4,
    "23473376":5,
    "23473373":6,
    "23473380":7,
    "23475095":9,
    "23475126":10,
    "23475104":11,
    "23494174":12,
    "23475128":14,
    "23475114":16,
}

ALL_DEVICES = [
    SIDE1_DEVICE, SIDE2_DEVICE, SIDE3_DEVICE, SIDE4_DEVICE, SIDE5_DEVICE,
    SIDE6_DEVICE, SIDE7_DEVICE, SIDE9_DEVICE, SIDE10_DEVICE, SIDE11_DEVICE,
    SIDE12_DEVICE, SIDE14_DEVICE, SIDE16_DEVICE,
]

camConfigs={"23475099":{"EXPOSURE":17000.0},
    "23475110":{"EXPOSURE":17000.0},
    "23473372":{"EXPOSURE":17000.0},
    "23475127":{"EXPOSURE":17000.0},
    "23473376":{"EXPOSURE":17000.0},
    "23473373":{"EXPOSURE":17000.0},
    "23473380":{"EXPOSURE":17000.0},
    "23475095":{"EXPOSURE":17000.0},
    "23475126":{"EXPOSURE":17000.0},
    "23475104":{"EXPOSURE":17000.0},
    "23494174":{"EXPOSURE":17000.0},
    "23475128":{"EXPOSURE":17000.0},
    "23475114":{"EXPOSURE":17000.0},}



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
        config_file_path = os.path.join(BASE_PATH, "config_one.xml")
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
            
def updatetrigger(process, complete):
    dbConnection = None
    cur = None
    try:
        dbConnection = getDatabaseConnection()
        cur = dbConnection.cursor()
        query = f"UPDATE FRAME_CAPTURE_STATUS_TABLE SET framecaptureonecomplete='{complete}' WHERE ID = '1';"
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
        query = f"UPDATE FRAME_CAPTURE_STATUS_TABLE SET framecaptureonecomplete='1', framecapturetwocomplete = '1', INFERENCE_STATUS = '1' WHERE ID = '1';"
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

def update_init_status(status):
    dbConnection = None
    cur = None

    try:
        dbConnection =getDatabaseConnection()
        cur = dbConnection.cursor()
        query = f"UPDATE HEALTH_STATUS_TABLE SET SYSTEM_STATUS='{status}' WHERE SYSTEM_NAME='CAMERA_INIT'"
        cur.execute(query)
        dbConnection.commit()
    except Exception as e:
        logger.critical("update_init_status() Exception is : "+ str(e))
        logger.critical(traceback.format_exc())
    finally:
        if cur is not None:
            cur.close()
        if dbConnection is not None:
            dbConnection.close()

def fetchtrigger():
    dbConnection = None
    cur = None
    processone = 0
    ENGINE_NUMBER = ""
    try:
        dbConnection = getDatabaseConnection()
        cur = dbConnection.cursor()
        query = f"SELECT framecapture, ENGINE_NUMBER FROM FRAME_CAPTURE_STATUS_TABLE;"
        cur.execute(query)
        data = cur.fetchone()
        processone = data[0]
        ENGINE_NUMBER = data[1]
    except Exception as e:
        logger.critical("fetchtrigger() Exception is : " + str(e))
        logger.critical(traceback.format_exc())
    finally:
        if cur is not None:
            cur.close()
        if dbConnection is not None:
            dbConnection.close()
    return processone, ENGINE_NUMBER

def configureMVCameraFlir(cam,reqConfig):
    global logger
    try:
        t1 = datetime.datetime.now()
        node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
        device_serial_number = node_device_serial_number.GetValue()
        cam.Init()
        tlStreamSetup=cam.GetTLStreamNodeMap()
        camNodeMap=cam.GetNodeMap()
        resendFramesNode=PySpin.CBooleanPtr(tlStreamSetup.GetNode("StreamPacketResendEnable"))
        if PySpin.IsAvailable(resendFramesNode) and PySpin.IsReadable(resendFramesNode) and PySpin.IsWritable(resendFramesNode):
            resendFramesNode.SetValue(False)
        deviceThroughput=PySpin.CIntegerPtr(cam.GetNodeMap().GetNode('DeviceLinkThroughputLimit'))
        if PySpin.IsAvailable(deviceThroughput) and PySpin.IsReadable(deviceThroughput) and PySpin.IsWritable(deviceThroughput):
            device_throughput=int(6500000)
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

        # Retrieve Buffer Handling Mode Information
        handling_mode = PySpin.CEnumerationPtr(tlStreamSetup.GetNode('StreamBufferHandlingMode'))
        handling_mode_entry = PySpin.CEnumEntryPtr(handling_mode.GetCurrentEntry())
        if PySpin.IsReadable(handling_mode) and PySpin.IsWritable(handling_mode):
            handling_mode_entry = handling_mode.GetEntryByName("NewestOnly")
            handling_mode.SetIntValue(handling_mode_entry.GetValue())
            print("Buffer Handling mode set")
        # Set stream buffer Count Mode to manual
        stream_buffer_count_mode = PySpin.CEnumerationPtr(tlStreamSetup.GetNode('StreamBufferCountMode'))
        stream_buffer_count_mode_manual = PySpin.CEnumEntryPtr(stream_buffer_count_mode.GetEntryByName('Manual'))
        if PySpin.IsReadable(stream_buffer_count_mode) and PySpin.IsWritable(stream_buffer_count_mode):
            stream_buffer_count_mode.SetIntValue(stream_buffer_count_mode_manual.GetValue())
            print('Stream Buffer Count Mode set to manual...')

        # Retrieve and modify Stream Buffer Count
        buffer_count = PySpin.CIntegerPtr(tlStreamSetup.GetNode('StreamBufferCountManual'))
        if PySpin.IsReadable(stream_buffer_count_mode) and PySpin.IsWritable(stream_buffer_count_mode):
            buffer_count.SetValue(100)
            print("buffer count set to 100")
        node_acquisition_mode=PySpin.CEnumerationPtr(camNodeMap.GetNode('AcquisitionMode'))
        if not PySpin.IsAvailable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
            print("Unable to set acquisition mode")
            logger.critical("Unable to set acquisition mode")
            return(False)

        node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous') #possible values "SingleFrame"
        if not PySpin.IsAvailable(node_acquisition_mode_continuous) or not PySpin.IsReadable(node_acquisition_mode_continuous):
            print('Unable to set acquisition mode to continuous i')
            logger.critical("Unable to set acquisition mode to continuous")
            return(False)
        acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()
        node_acquisition_mode.SetIntValue(acquisition_mode_continuous)
        #switch off exposure auto
        ExposureAuto=PySpin.CEnumerationPtr(camNodeMap.GetNode("ExposureAuto"))
        if PySpin.IsAvailable(ExposureAuto) and PySpin.IsReadable(ExposureAuto) and PySpin.IsWritable(ExposureAuto):
            exposureAutoOff=ExposureAuto.GetEntryByName("Off")
            if PySpin.IsAvailable(exposureAutoOff) and PySpin.IsReadable(exposureAutoOff):
                exposureAutoOffVal=exposureAutoOff.GetValue()
                ExposureAuto.SetIntValue(exposureAutoOffVal)
        ExposureTime=PySpin.CFloatPtr(camNodeMap.GetNode("ExposureTime"))
        if PySpin.IsAvailable(ExposureTime) and PySpin.IsReadable(ExposureTime) and PySpin.IsWritable(ExposureTime):
            requiredExposureVal=float(reqConfig.get("EXPOSURE"))
            if requiredExposureVal>=ExposureTime.GetMin() and requiredExposureVal<=ExposureTime.GetMax():
                ExposureTime.SetValue(requiredExposureVal)
            else:
                logger.critical("Incorrect exposure in config- setting to min value.")
                ExposureTime.SetValue(ExposureTime.GetMin())

        #black fly s settings
        #Set Frame rate
        AcquisitionFrameRateEnable=PySpin.CBooleanPtr(camNodeMap.GetNode("AcquisitionFrameRateEnable"))
        if PySpin.IsAvailable(AcquisitionFrameRateEnable) and PySpin.IsReadable(AcquisitionFrameRateEnable) and PySpin.IsWritable(AcquisitionFrameRateEnable):
            AcquisitionFrameRateEnable.SetValue(True)
        
        AcquisitionFrameRate=PySpin.CFloatPtr(camNodeMap.GetNode("AcquisitionFrameRate"))
        if PySpin.IsAvailable(AcquisitionFrameRate) and PySpin.IsReadable(AcquisitionFrameRate) and PySpin.IsWritable(AcquisitionFrameRate):
            reqFrameRate=float(1.0)
            if reqFrameRate>=AcquisitionFrameRate.GetMin() and reqFrameRate<=AcquisitionFrameRate.GetMax():
                AcquisitionFrameRate.SetValue(reqFrameRate)
            else:
                logger.critical(f"Incorrect frame rate in config-{device_serial_number} setting to min value.")
                AcquisitionFrameRate.SetValue(AcquisitionFrameRate.GetMin())
        
        # Pixel Format
        # GHC packet size
        PixelFormat=PySpin.CEnumerationPtr(camNodeMap.GetNode("PixelFormat"))
        if PySpin.IsAvailable(PixelFormat) and PySpin.IsReadable(PixelFormat) and PySpin.IsWritable(PixelFormat):
            PixelFormat_BayerRG8=PixelFormat.GetEntryByName("BayerRG8")
            if PySpin.IsAvailable(PixelFormat_BayerRG8) and PySpin.IsReadable(PixelFormat_BayerRG8) and PySpin.IsWritable(PixelFormat_BayerRG8):
                PixelFormat_BayerRG8_val=PixelFormat_BayerRG8.GetValue()
                PixelFormat.SetIntValue(PixelFormat_BayerRG8_val)
        # logger.debug(f"time taken to config all the cameras :: {(datetime.datetime.now() - t1).total_seconds() }")
        return(True)
            
        
    except Exception as e:
        logger.critical(f"Error in getting configs:{e}")
        logger.critical(traceback.format_exc())
        print(f"Error in getting configs:{e}")
        print(traceback.format_exc())
        return(None)

def releaseFlirInstance(flirSystem):
    if flirSystem is not None:
        # Release system instance
        flirSystem.ReleaseInstance()
        print("System released")
        return(True)
    else:
        return(False)
def mainFunction():
    # Create dummy folder
    update_init_status("ACTIVE")
    dummy_folder = os.path.join(configHashMap.get(CONFIG_KEY_NAME.RAW_IMAGE_PATH), "INIT_CAPTURE")
    if not os.path.exists(dummy_folder):
        os.makedirs(dummy_folder)

    # Initialize camera
    flirCamList=None
    flirSystem=None
    flirSystem = PySpin.System.GetInstance()
    flirCamList =flirSystem.GetCameras()
    flirCamObjects=[]
    for cam in flirCamList:
        serialNode=PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode("DeviceSerialNumber"))
        camSrNum=serialNode.GetValue()
        if camSrNum in ALL_DEVICES:
            flirCamObjects.append(cam)
    #configure cameras
    #flir configuration
    t1 = datetime.datetime.now()
    for cam in flirCamObjects:
        camGetTLDeviceNodeMap=cam.GetTLDeviceNodeMap()
        camSerialNumPtr=PySpin.CStringPtr(camGetTLDeviceNodeMap.GetNode("DeviceSerialNumber"))
        camSerialNum=camSerialNumPtr.GetValue()
        currentConfig=camConfigs.get(camSerialNum)
        # cam.Init()
        # time.sleep(0.01)
        # if not cam.IsStreaming():
        #     cam.BeginAcquisition()
        camConfigured=configureMVCameraFlir(cam,currentConfig)
        
    logger.debug(f"time taken to config all the cameras :: {(datetime.datetime.now() - t1).total_seconds() }")
    time.sleep(1)
    # dummy capture
    processor = PySpin.ImageProcessor()
    processor.SetColorProcessing(PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR)
    
    t1 = datetime.datetime.now()
    
    
    for cam in flirCamObjects:
        maxatempt=5
        currattempt=0
        while currattempt<maxatempt:
            node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
            device_serial_number=""
            if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
                device_serial_number = node_device_serial_number.GetValue()
            if not cam.IsStreaming():
                cam.BeginAcquisition()

            image_result = None
            try:
                image_result = cam.GetNextImage(5000)
                if image_result.IsIncomplete():
                    errorText=str(f"Image incomplete in Flir camera:{device_serial_number}")
                    # camlogger.critical(errorText)
                else:
                    image_converted = processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                    fileName = f"{dummy_folder}/IMG_{DEVICE_NUM[device_serial_number]}.jpeg"
                    img = image_converted.GetNDArray()
                    cv2.imwrite(fileName, img)
                    currattempt=5
                    # image_nd=cv2.cvtColor(image_nd,cv2.COLOR_BayerRG2RGBA)
                    
                    # if filename!="":
                    #     cv2.imwrite(filename, image_nd)
                time.sleep(0.002)
            except Exception as e:
                logger.critical(f"Error in FLIR image:{e}")
                logger.critical(traceback.format_exc())
            finally:
                currattempt+=1
                if image_result is not None:
                    image_result.Release()
            time.sleep(0.005)

            
    logger.debug(f"time taken to capture all dummy images the cameras :: {(datetime.datetime.now() - t1).total_seconds() }")
                                
    previous_vin_number = ""
    last_capture = datetime.datetime.now()
    update_init_status("INACTIVE")
    while True:
        try:
            print("------------------------------ NEW LOOP ------------------------------")
            start, vin_number = fetchtrigger()
            print(f"vin_number -- {vin_number}")

            if start == 1 and vin_number != "EMPTY" and vin_number != "DUMMY" and vin_number != previous_vin_number:
                logger.debug(f"vin_number -- {vin_number}")
                vin_folder = os.path.join(configHashMap.get(CONFIG_KEY_NAME.RAW_IMAGE_PATH), vin_number)
                if not os.path.exists(vin_folder):
                    os.makedirs(vin_folder)

                # Reinitialize camera only if necessary
                # cam_inst.capture_images(vin_folder)
                t1 = datetime.datetime.now()
                for cam in flirCamObjects:
                    maxatempt=5
                    currattempt=0
                    while currattempt<maxatempt:
                        node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                        device_serial_number=""
                        if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
                            device_serial_number = node_device_serial_number.GetValue()

                        logger.debug(f"Starting Capture --- {currattempt} for {device_serial_number}")
                        if not cam.IsStreaming():
                            cam.BeginAcquisition()
                        try:
                            image_result = cam.GetNextImage(5000)
                            if image_result.IsIncomplete():
                                errorText=str(f"Image incomplete in Flir camera:{device_serial_number}")
                                logger.critical(errorText)
                            else:
                                image_converted = processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                                fileName = f"{vin_folder}/IMG_{DEVICE_NUM[device_serial_number]}.jpeg"
                                img = image_converted.GetNDArray()
                                cv2.imwrite(fileName, img)
                                currattempt=5
                                # image_nd=cv2.cvtColor(image_nd,cv2.COLOR_BayerRG2RGBA)
                                
                                # if filename!="":
                                #     cv2.imwrite(filename, image_nd)
                        except Exception as e:
                            logger.critical(f"Error in FLIR image:{e}")
                            logger.critical(traceback.format_exc())
                        finally:
                            currattempt+=1
                            if image_result is not None:
                                image_result.Release()
                        time.sleep(0.005)

                logger.debug(f"time taken to capture all the cameras :: {(datetime.datetime.now() - t1).total_seconds() }")

                if len(os.listdir(vin_folder)) != 13: break

                last_capture = datetime.datetime.now()
                logger.debug(f"Added {len(os.listdir(vin_folder))} images to -- {vin_folder}")
                print(f"Added images to -- {vin_folder}")

                updatetrigger(process=0, complete=1)
                previous_vin_number = vin_number

                # Update trigger files
                try:
                    if os.path.exists(configHashMap.get(CONFIG_KEY_NAME.UI_TRIGGER_FILE_PATH)):
                        os.remove(configHashMap.get(CONFIG_KEY_NAME.UI_TRIGGER_FILE_PATH))
                    with open(configHashMap.get(CONFIG_KEY_NAME.UI_TRIGGER_FILE_PATH), "w") as trigger_file:
                        trigger_file.write(vin_number)

                    if os.path.exists(configHashMap.get(CONFIG_KEY_NAME.TRIGGER_FILE_PATH)):
                        os.remove(configHashMap.get(CONFIG_KEY_NAME.TRIGGER_FILE_PATH))
                    with open(configHashMap.get(CONFIG_KEY_NAME.TRIGGER_FILE_PATH), "w") as trigger_file:
                        trigger_file.write(vin_number)
                except Exception as e:
                    logger.error(f"Error updating trigger files: {e}")
                    logger.critical(traceback.format_exc())

                updateAllTriggerStatus()

            else:
                
                currDateTime = datetime.datetime.now()
                hour = int(currDateTime.hour)
                minute = int(currDateTime.minute)

                if hour == 6 and minute > 10 and minute < 15: break
                if (datetime.datetime.now() - last_capture).total_seconds() > 3600: break

            time.sleep(1)  # Prevent tight loop

        except Exception as E:
            logger.critical(f"Main loop error:{E}")
            logger.critical(traceback.format_exc())
            break

    # removing all flir references
    while flirCamObjects:
        cam = flirCamObjects.pop()
        if cam.IsStreaming():
            cam.EndAcquisition()
        if cam.IsInitialized():
            cam.DeInit()
        del cam
        time.sleep(0.5)

    del flirCamObjects
    flirCamObjects=None
    if flirCamList is not None:
        flirCamList.Clear()
    del flirCamList
    flirCamList=None

    logger.debug("All instance of flir cam removed.")
    gc.collect()
    time.sleep(1)
    
    flirRelaeseThread=threading.Thread(target=releaseFlirInstance,args=(flirSystem,))
    flirRelaeseThread.daemon=True
    flirRelaeseThread.start()
    flirRelaeseThread.join(30)

    if flirRelaeseThread.is_alive():
        logger.debug("Flirsystem stuck.")
    else:
        logger.debug("Flirsystem released.")

if __name__ == "__main__":
    loadConfiguration()
    initializeLogger()
    while True:
        try:
            mainFunction()
            logger.debug(f"Main function completed successfully, exiting loop. POE was shut down")
        except Exception as e:
            logger.critical(f"Exception in mainFunction: {e}")
            logger.critical(traceback.format_exc())
            time.sleep(2)
            continue

    # mainFunction()