import subprocess
import time
import cv2
import os
import logging
from pypylon import pylon
import traceback
import queue
import shutil
from datetime import datetime
import xml.etree.ElementTree as ET
import pymysql
import logging,traceback
from logging import handlers
# from frame_capture_mail_sender import CameraMailSender

img_number = -1
async_q = queue.Queue()
grab_state = True
frame_ctr = 0
frame_logger = None
cam_count = 1
debugMode = False
configHashMap = {}

processID = os.getpid()
print("This process has the PID", processID)

def initializeLogger():
    global logger, configHashMap
    try:
        ''' Initializing Logger '''
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.setLevel(logging.ERROR)
        # Define the log file format
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Create a TimedRotatingFileHandler for daily rotation
        log_file = configHashMap.get(CONFIG_KEY_NAME.LOG_FILE_PATH) + os.path.basename(__file__[:-2]) + "log"
        file_handler = handlers.TimedRotatingFileHandler(log_file, when='midnight', backupCount=configHashMap.get(CONFIG_KEY_NAME.LOG_BACKUP_COUNT))
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        print("BaslerSingleCam Module Initialized...")
        logger.debug("BaslerSingleCam Module Initialized")

    except Exception as e:
        print(f"initializeLogger() Exception is {e}")
        print(traceback.format_exc())

        
class CONFIG_KEY_NAME:
    CODE_PATH = "CODE_PATH"
    LOG_FILE_PATH = "LOG_FILE_PATH"
    LOG_BACKUP_COUNT = "LOG_BACKUP_COUNT"
    CAM_SERIAL_NO = "CAM_SERIAL_NO"
    CAM_NAME = "CAM_NAME"
    EXPOSURE = "EXPOSURE"
    FRAME_RATE = "FRAME_RATE"
    SAVE_LIVE_IMG_PATH = "SAVE_LIVE_IMG_PATH"
    UI_PATH = "UI_PATH"
    INF_PATH = "INF_PATH"
    RAW_IMG_PATH = "RAW_IMG_PATH"
    DB_USER = "DB_USER"
    DB_PASS = "DB_PASS"
    DB_HOST = "DB_HOST"
    DB_NAME = "DB_NAME"

def loadConfiguration():
    global configHashMap
    try:
        current_directory = os.getcwd()
        # print("current_directory", current_directory)
        config_file_path = os.path.join(current_directory, "BASLER_CONFIG.xml")
        if debugMode is True:
            config_file_path = os.path.join(current_directory, "BASLER_CONFIG.xml")
        config_parse = ET.parse(config_file_path)
        config_root = config_parse.getroot()
        
        configHashMap[CONFIG_KEY_NAME.CODE_PATH] = config_root[0].text
        configHashMap[CONFIG_KEY_NAME.LOG_FILE_PATH] = config_root[1].text
        configHashMap[CONFIG_KEY_NAME.LOG_BACKUP_COUNT] = int(config_root[2].text)
        configHashMap[CONFIG_KEY_NAME.CAM_SERIAL_NO] = str(config_root[3].text)
        configHashMap[CONFIG_KEY_NAME.CAM_NAME] = config_root[4].text
        configHashMap[CONFIG_KEY_NAME.EXPOSURE] = int(config_root[5].text)
        configHashMap[CONFIG_KEY_NAME.FRAME_RATE] = float(config_root[6].text)
        configHashMap[CONFIG_KEY_NAME.SAVE_LIVE_IMG_PATH] = config_root[7].text
        configHashMap[CONFIG_KEY_NAME.UI_PATH] = config_root[8].text
        configHashMap[CONFIG_KEY_NAME.INF_PATH] = config_root[9].text
        configHashMap[CONFIG_KEY_NAME.RAW_IMG_PATH] = config_root[10].text
        configHashMap[CONFIG_KEY_NAME.DB_USER] = config_root[11].text
        configHashMap[CONFIG_KEY_NAME.DB_PASS] = config_root[12].text
        configHashMap[CONFIG_KEY_NAME.DB_HOST] = config_root[13].text
        configHashMap[CONFIG_KEY_NAME.DB_NAME] = config_root[14].text
        # print(f"configHashMap {configHashMap}")

    except Exception as e:
        print(f"loadConfiguration() Exception is {e}")
        print(traceback.format_exc()) 


class BaslerCam:
    global grab_state
    def __init__(self):
        global grab_state
        grab_state = True
        # self.clear_raw_frames()
    
    def initCam(self):
        try:
            CAM_SERIAL_NO = None
            CAM_SERIAL_NO = configHashMap.get(CONFIG_KEY_NAME.CAM_SERIAL_NO)

            for i in pylon.TlFactory.GetInstance().EnumerateDevices():
                if i.GetSerialNumber() == CAM_SERIAL_NO:
                    CAM_SERIAL_NO = i
                    try:
                        CAM_SERIAL_NO = i
                    except Exception as e:
                        logging.error("cam1 error: %s", str(e))
                        print("cam1 error: "+str(e))

            self.startFrameGrabbing(CAM_SERIAL_NO)
            
        except Exception as e:
            logging.error("main() Exception : %s", str(e))
            

    def getDatabaseConnection(self):
        global configHashMap
        dbConnection = None
        try:
            dbConnection = pymysql.connect(
                host = configHashMap.get(CONFIG_KEY_NAME.DB_HOST),
                user = configHashMap.get(CONFIG_KEY_NAME.DB_USER), 
                passwd = configHashMap.get(CONFIG_KEY_NAME.DB_PASS),
                db = configHashMap.get(CONFIG_KEY_NAME.DB_NAME))
            
        except Exception as e:
            print(e)
            # logger.critical("getDatabaseConnection() Exception is : "+ str(e))
            logger.critical(traceback.format_exc())

        return dbConnection
    
    def updateHealthStatus(self, health, is_data_sync):
        global configHashMap
        dbConn = None
        cur  = None
        item = configHashMap.get(CONFIG_KEY_NAME.CAM_SERIAL_NO)
        try:
            dbConn = self.getDatabaseConnection()
            cur = dbConn.cursor()
            item = str(item).strip()
            health = str(health).strip()
            is_data_sync = int(is_data_sync)  # Ensure this is an integer

            update_query = """
                UPDATE tadipatri_health_status_table
                SET HEALTH = %s, IS_DATA_SYNC = %s, CREATE_DATETIME = NOW()
                WHERE ITEM = %s
            """
            
            cur.execute(update_query, (health, is_data_sync, item))
            
            dbConn.commit()
            print(f"Record updated successfully for ITEM: {item}")

        except pymysql.MySQLError as e:
            print(f"Error occurred while updating record: {e}")
            logger.critical(traceback.format_exc())

        finally:
            self.closeDBConnection(cur, dbConn)
    
    def closeDBConnection(self, cursor, dbConn):
        try:
            if cursor:
                cursor.close()
            if dbConn:
                dbConn.close()

        except Exception as error:
            print(error)
            logger.error(traceback.print_exc())    
            
    def startFrameGrabbing(self, CAM_SERIAL_NO):
        global FRAME_LOCATION
        cnt = 1
        FRAME_RATE =  configHashMap.get(CONFIG_KEY_NAME.FRAME_RATE)
        EXPOSURE = configHashMap.get(CONFIG_KEY_NAME.EXPOSURE)

        try:
            # VERY IMPORTANT STEP! To use Basler PyPylon OpenCV viewer you have to call .Open() method on you camera
            if CAM_SERIAL_NO is not None:
                try:
                    CAM_SERIAL_NO = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(CAM_SERIAL_NO))
                    CAM_SERIAL_NO.Open()
                    CAM_SERIAL_NO.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                    CAM_SERIAL_NO.AcquisitionFrameRateEnable = True
                    CAM_SERIAL_NO.AcquisitionFrameRateAbs = FRAME_RATE
                    CAM_SERIAL_NO.ExposureTimeAbs.SetValue(EXPOSURE) 
                    print("here no error")
                except Exception as error:
                    tb = traceback.format_exc()
                    # Extracting detailed information
                    exception_message = str(error)
                    last_traceback = traceback.extract_tb(error.__traceback__)[-1]  # Get the last traceback frame
                    function_name = last_traceback.name
                    line_number = last_traceback.lineno
                    filename = last_traceback.filename
                    detailed_error_message = (f"Error occurred in function '{function_name}' in {filename}, "
                                            f"at line {line_number}: {exception_message}\n\nTraceback:\n{tb}")
                    logger.critical(detailed_error_message)
                    print(detailed_error_message)
                    # mail_sender = CameraMailSender()
                    # mail_sender.send_camera_error_email(detailed_error_message, CameraName)
                    # subprocess.run(["/bin/bash", "/home/dpc-narmada/INSIGHTZZ/Code/Shell_Script/Basler_Cam_Restart.sh"])

            converter = pylon.ImageFormatConverter()
            converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            start_time = int(time.time())
            threshold_time = 600
            while True:
                ############# Top Post ###################
                try:
                    cycle_data = "/home/ultratech-tadipatri/insightzz/DPC-PROJECT/TempRawData/ContinousData/Left"
                    cnt = cnt + 1
                    if CAM_SERIAL_NO.IsGrabbing():
                        grabResult = CAM_SERIAL_NO.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
                    if grabResult.GrabSucceeded():
                        image = converter.Convert(grabResult)
                        img = image.GetArray()
                        # save image for live UI 
                        save_live_img_path = configHashMap.get(CONFIG_KEY_NAME.SAVE_LIVE_IMG_PATH)
                        cv2.imwrite(f"{save_live_img_path}/IMG_1.jpg", img)
                        save_ui_img_path = configHashMap.get(CONFIG_KEY_NAME.UI_PATH)

                        if len(os.listdir(save_ui_img_path)) == 0:
                            shutil.copy2(f"{save_live_img_path}/IMG_1.jpg", f"{save_ui_img_path}/IMG_1.jpg")

                        save_infer_img_path = configHashMap.get(CONFIG_KEY_NAME.INF_PATH)
                        if len(os.listdir(save_infer_img_path)) == 0:
                            shutil.copy2(f"{save_live_img_path}/IMG_1.jpg", f"{save_infer_img_path}/IMG_1.jpg")
                        # shutil.copy2(f"{save_live_img_path}/IMG_1.jpg", f"{cycle_data}/{datetime.now().strftime('%Y_%m_%d_%H_%M_%S_%f')}.jpg")
                        
                        save_raw_img_path = configHashMap.get(CONFIG_KEY_NAME.RAW_IMG_PATH)
                        shutil.copy2(f"{save_live_img_path}/IMG_1.jpg", f"{save_raw_img_path}/{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.jpg")
                        # shutil.copy2(f"{save_live_img_path}/IMG_1.jpg", f"{cycle_data}/{datetime.now().strftime('%Y_%m_%d_%H_%M_%S_%f')}.jpg")
                        print("img copied...")

                        health_status = "OK"
                        current_time = int(time.time())
                        if current_time - start_time > threshold_time:
                            self.updateHealthStatus(health_status, 0)
                            start_time = int(time.time())

                    if(CAM_SERIAL_NO is not None):
                        grabResult.Release()

                except Exception as e:
                    print(f"Error {e}")
                    logger.critical("Error in While Loop")
                    logger.critical(traceback.format_exc())
                    break

            if(CAM_SERIAL_NO is not None):
                CAM_SERIAL_NO.StopGrabbing()
                CAM_SERIAL_NO.close() 
   
            self.initCam()            
            
        except Exception as error:
            tb = traceback.format_exc()
            exception_message = str(error)
            last_traceback = traceback.extract_tb(error.__traceback__)[-1]  # Get the last traceback frame
            function_name = last_traceback.name
            line_number = last_traceback.lineno
            filename = last_traceback.filename
            detailed_error_message = (f"Error occurred in function '{function_name}' in {filename}, "
                                    f"at line {line_number}: {exception_message}\n\nTraceback:\n{tb}")
            
            health_status = "NOK"
            current_time = int(time.time())
            if current_time - start_time > threshold_time:
                self.updateHealthStatus(health_status, 0)
                start_time = int(time.time())

            # mail_sender = CameraMailSender()
            # mail_sender.send_camera_error_email(detailed_error_message, CameraName)
            # logger.critical("Error in startFrameGrabbing")
            # logger.critical(traceback.format_exc())
            # subprocess.run(["/bin/bash", "/home/dpc-narmada/INSIGHTZZ/Code/Shell_Script/Basler_Cam_Restart.sh"])
            # print("Error in startFrameGrabbing")
            # print(traceback.format_exc()) 
            
    def runModule(self):
        self.initCam()

if __name__ == "__main__":
    loadConfiguration()
    initializeLogger()
    basler_cam_obj = BaslerCam()
    basler_cam_obj.runModule()
