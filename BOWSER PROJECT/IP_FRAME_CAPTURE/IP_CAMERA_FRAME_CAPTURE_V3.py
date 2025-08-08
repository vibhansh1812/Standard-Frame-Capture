import cv2
import os, sys
import queue
import threading
import time
import datetime
import logging
from logging import handlers
import shutil

module_stop=False

cam_ip_101 = None
cam_ip_102 = None

FRONT_CAM_IP='192.168.1.105'
TOP_CAM_IP='192.168.1.106'

USERNAME = "admin"
PASSWORD = "insightzz@123"

CAMERA_NAME_101 = "CAMERA_NAME_101"
CAMERA_NAME_102 = "CAMERA_NAME_102"

debugMode = False
log_name=os.path.basename(__file__[:-2])+"log"
logger=logging.getLogger(log_name[:-4])
if debugMode==True:
    log_level=logging.DEBUG
else:
    log_level=logging.ERROR

logger.setLevel(log_level)
log_format=logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log_fl=handlers.RotatingFileHandler(log_name,maxBytes=1048576,backupCount=5) # 1MB log files max
log_fl.setFormatter(log_format)
log_fl.setLevel(log_level)
logger.addHandler(log_fl)
logger.critical("Frame Capture Module Initialized")

BASE_SAVE_PATH = "/home/bowaser-inspection/INSIGHTZZ/CODE/ALGORITHM/IP_IMG/"

class BufferLessVideoCapture:
    def __init__(self, name):
        self.cap = cv2.VideoCapture(name)

def initCAM():
    global cam_ip_101, cam_ip_102
    
    try:    
        cam_ip_101=BufferLessVideoCapture(f"rtsp://{USERNAME}:{PASSWORD}@{FRONT_CAM_IP}/Streaming/Channels/1")
    except Exception as e:
        logger.critical("Exception in init of cam cam_ip_101 "+ str(e))
    if cam_ip_101.cap is None or not cam_ip_101.cap.isOpened():
        print("Warning: unable to open video source")
        # update_Cam_Status(2,"NOT OK")
    else:
        pass #update_Cam_Status(2,"OK")

    try:    
        cam_ip_102=BufferLessVideoCapture(f"rtsp://{USERNAME}:{PASSWORD}@{TOP_CAM_IP}/Streaming/Channels/1")
    except Exception as e:
        logger.critical("Exception in init of cam cam_ip_102 "+ str(e))
    if cam_ip_102.cap is None or not cam_ip_102.cap.isOpened():
        print("Warning: unable to open video source")
        # update_Cam_Status(4,"NOT OK")
    else:
        pass # update_Cam_Status(4,"OK")

def cam_ip_101_save():
    global cam_ip_101, module_stop
    fiveSecDiff = datetime.timedelta(seconds=5)
    START_FRAMECAPTURE_DATETIME = datetime.datetime.now()
    print(f"cam_ip_101() Started again at : {datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}")
    while not(module_stop):
        ret,frame=cam_ip_101.cap.read()
        time.sleep(0.001)
        try:
            if ret:
                cv2.imwrite(f"{BASE_SAVE_PATH}CAM_101/TMP.jpg",frame)
                START_FRAMECAPTURE_DATETIME = datetime.datetime.now()
                if os.listdir(f"{BASE_SAVE_PATH}CAM_101/TMP/") == []:
                    shutil.copyfile(f"{BASE_SAVE_PATH}CAM_101/TMP.jpg",f"{BASE_SAVE_PATH}CAM_101/TMP/TMP.jpg")
            else:
                timeDiff = datetime.datetime.now() - START_FRAMECAPTURE_DATETIME
                if timeDiff > fiveSecDiff:
                    START_FRAMECAPTURE_DATETIME = datetime.datetime.now()
                    print(f"cam_ip_101_save() Frame Capture Module Stopped, Re-starting it again at : {datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}")
                    module_stop = True
        except Exception as e:
            logger.critical("Exception in cam_ip_101 save "+ str(e))

def cam_ip_102_save():
    global cam_ip_102, module_stop
    fiveSecDiff = datetime.timedelta(seconds=5)
    START_FRAMECAPTURE_DATETIME = datetime.datetime.now()
    print(f"cam_ip_102_save() Started again at : {datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}")
    while not(module_stop):
        ret,frame=cam_ip_102.cap.read()
        time.sleep(0.001)
        try:
            if ret:
                cv2.imwrite(f"{BASE_SAVE_PATH}CAM_102/TMP.jpg",frame)
                START_FRAMECAPTURE_DATETIME = datetime.datetime.now()
                if os.listdir(f"{BASE_SAVE_PATH}CAM_102/TMP/") == []:
                    shutil.copyfile(f"{BASE_SAVE_PATH}CAM_102/TMP.jpg",f"{BASE_SAVE_PATH}CAM_102/TMP/TMP.jpg")
            else:
                timeDiff = datetime.datetime.now() - START_FRAMECAPTURE_DATETIME
                if timeDiff > fiveSecDiff:
                    START_FRAMECAPTURE_DATETIME = datetime.datetime.now()
                    print(f"CAM_102_save() Frame Capture Module Stopped, Re-starting it again at : {datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}")
                    module_stop = True
        except Exception as e:
            logger.critical("Exception in CAM_102 save "+ str(e))
        
def mainFunction():
    global module_stop
    initCAM()
    while(True):
        try:
            t1=time.time()*1000
            cam_ip_101_thread=threading.Thread(target=cam_ip_101_save,args=())
            cam_ip_101_thread.start()
            cam_ip_102_thread=threading.Thread(target=cam_ip_102_save,args=())
            cam_ip_102_thread.start()
            
            cam_ip_101_thread.join()
            cam_ip_102_thread.join()
            
            print(f"Last Thread Running Time : {time.time()*1000-t1}")
            if module_stop is True:
                print("Code Exited")
                break
        except Exception as e:
            logger.critical(str(e))
            pass


if __name__=="__main__":
    mainFunction()

