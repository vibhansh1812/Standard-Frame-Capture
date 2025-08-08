from logging import handlers
import os
import PySpin
import time 
import cv2
import logging
import traceback
from logging.handlers import RotatingFileHandler
from multiprocessing.dummy import Process
import xml.etree.ElementTree as ET
from subprocess import Popen, PIPE
import threading
from datetime import timedelta, datetime
import pymysql
import shutil

# from frame_capture_mail_sender import CameraMailSender

''' Process ID and Base Code Path '''
PROCESS_ID = os.getpid()
BASE_PATH = os.getcwd()
configHashMap = {}
debugMode = False
# if not os.path.exists(SAVED_SITE_1_PATH):
#     os.mkdir(SAVED_SITE_1_PATH)

# def initializeLogger():
#     global logger, configHashMap
#     try:
#         ''' Initializing Logger '''
#         logger = logging.getLogger(__name__)
#         logger.setLevel(logging.DEBUG)
#         #logger.setLevel(logging.ERROR)
#         # Define the log file format
#         formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
#         # Create a TimedRotatingFileHandler for daily rotation
#         log_file = configHashMap.get(CONFIG_KEY_NAME.LOG_FILE_PATH) + os.path.basename(__file__[:-2]) + "log"
#         file_handler = handlers.TimedRotatingFileHandler(log_file, when='midnight', backupCount=configHashMap.get(CONFIG_KEY_NAME.LOG_BACKUP_COUNT))
#         file_handler.setLevel(logging.DEBUG)
#         file_handler.setFormatter(formatter)
#         logger.addHandler(file_handler)
#         print("FlirCam Module Initialized...")
#         logger.debug("FlirCam Module Initialized")

#     except Exception as e:
#         print(f"initializeLogger() Exception is {e}")
#         print(traceback.format_exc())

        
class CONFIG_KEY_NAME:
    DB_USER = "DB_USER"
    DB_PASS = "DB_PASS"
    DB_HOST = "DB_HOST"
    DB_NAME = "DB_NAME"

    CODE_PATH = "CODE_PATH"
    LOG_FILE_PATH = "LOG_FILE_PATH"
    LOG_BACKUP_COUNT = "LOG_BACKUP_COUNT"
    CAM_SERIAL_NO = "CAM_SERIAL_NO"
    INTERFACE_NAME = "INTERFACE_NAME"
    CAM_NAME = "CAM_NAME"
    EXPOSURE = "EXPOSURE"
    FRAME_RATE = "FRAME_RATE"
    DEVICE_THROUGHPUT_VALUE = "DEVICE_THROUGHPUT_VALUE"
    SAVE_LIVE_IMG_PATH = "SAVE_LIVE_IMG_PATH"
    UI_PATH = "UI_PATH"
    INF_PATH = "INF_PATH"
    RAW_IMG_PATH = "RAW_IMG_PATH"

def loadConfiguration(logger):
    global configHashMap
    try:
        current_directory = os.getcwd()
        # print("current_directory", current_directory)
        config_file_path = os.path.join(current_directory, "FLIR_CONFIG.xml")
        if debugMode is True:
            config_file_path = os.path.join(current_directory, "FLIR_CONFIG.xml")
        config_parse = ET.parse(config_file_path)
        config_root = config_parse.getroot()
        
        configHashMap[CONFIG_KEY_NAME.DB_USER] = config_root[0][0].text
        configHashMap[CONFIG_KEY_NAME.DB_PASS] = config_root[0][1].text
        configHashMap[CONFIG_KEY_NAME.DB_HOST] = config_root[0][2].text
        configHashMap[CONFIG_KEY_NAME.DB_NAME] = config_root[0][3].text

        configHashMap[CONFIG_KEY_NAME.CODE_PATH] = config_root[1][0].text
        configHashMap[CONFIG_KEY_NAME.LOG_FILE_PATH] = config_root[1][1].text
        configHashMap[CONFIG_KEY_NAME.LOG_BACKUP_COUNT] = int(config_root[1][2].text)
        configHashMap[CONFIG_KEY_NAME.CAM_SERIAL_NO] = str(config_root[1][3].text)
        configHashMap[CONFIG_KEY_NAME.INTERFACE_NAME] = str(config_root[1][4].text)
        configHashMap[CONFIG_KEY_NAME.CAM_NAME] = config_root[1][5].text
        configHashMap[CONFIG_KEY_NAME.EXPOSURE] = int(config_root[1][6].text)
        configHashMap[CONFIG_KEY_NAME.FRAME_RATE] = float(config_root[1][7].text)
        configHashMap[CONFIG_KEY_NAME.DEVICE_THROUGHPUT_VALUE] = int(config_root[1][8].text)
        configHashMap[CONFIG_KEY_NAME.SAVE_LIVE_IMG_PATH] = config_root[1][9].text
        configHashMap[CONFIG_KEY_NAME.UI_PATH] = config_root[1][10].text
        configHashMap[CONFIG_KEY_NAME.INF_PATH] = config_root[1][11].text
        configHashMap[CONFIG_KEY_NAME.RAW_IMG_PATH] = config_root[1][12].text
        print(f"configHashMap {configHashMap}")

    except Exception as e:
        logger.critical(f"loadConfiguration() Exception is {e}")
        logger.critical(traceback.format_exc()) 

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

''' Database Funcation Start'''
def getDatabaseConnection():
    ''' DB credentials '''
    db_user = configHashMap.get(CONFIG_KEY_NAME.DB_USER)
    db_pass = configHashMap.get(CONFIG_KEY_NAME.DB_PASS)
    db_host = configHashMap.get(CONFIG_KEY_NAME.DB_HOST)
    db_name = configHashMap.get(CONFIG_KEY_NAME.DB_NAME)

    dbConnection = None
    try:
        dbConnection = pymysql.connect(host=db_host,user=db_user, passwd=db_pass,db= db_name)
    except Exception as e:
        print("getDatabaseConnection() Exception is : "+ str(e))
    return dbConnection

def getSubDirectoryPath(path, ParentDirName):
    mydir = os.path.join(path, ParentDirName+"/")
    if os.path.isdir(mydir) is not True:
        os.makedirs(mydir)
    return mydir

class FlirCam():
    Frame = None
    stopThread = False

    def __init__(self):
        self.data_collection = False
        try:
            t1 = threading.Thread(target = self.initCam)
            t1.start()
        except Exception as e:
            logger.error(traceback.format_exc())
    ''' Database Funcation Start'''
    def getDatabaseConnection(self):
        ''' DB credentials '''
        db_user = configHashMap.get(CONFIG_KEY_NAME.DB_USER)
        db_pass = configHashMap.get(CONFIG_KEY_NAME.DB_PASS)
        db_host = configHashMap.get(CONFIG_KEY_NAME.DB_HOST)
        db_name = configHashMap.get(CONFIG_KEY_NAME.DB_NAME)

        dbConnection = None
        try:
            dbConnection = pymysql.connect(host=db_host,user=db_user, passwd=db_pass,db= db_name)
        except Exception as e:
            print("getDatabaseConnection() Exception is : "+ str(e))
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

    def configure_exposure(self, cam, exposure_value):
        try:
            result = True
            if cam.ExposureAuto.GetAccessMode() != PySpin.RW:
                return False

            cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)

            if cam.ExposureTime.GetAccessMode() != PySpin.RW:
                return False

            exposure_time_to_set = exposure_value
            exposure_time_to_set = min(cam.ExposureTime.GetMax(), exposure_time_to_set)
            cam.ExposureTime.SetValue(exposure_time_to_set)

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            logger.error(traceback.format_exc())
            logger('Error: %s' % ex)
            result = False
        return result
        
    def acquire_images(self, cam_list):
        try:
            result = True
            CAM_SERIAL_NO = configHashMap.get(CONFIG_KEY_NAME.CAM_SERIAL_NO)
            DEVICE_THROUGHPUT_VALUE = configHashMap.get(CONFIG_KEY_NAME.DEVICE_THROUGHPUT_VALUE)
            FRAME_RATE = configHashMap.get(CONFIG_KEY_NAME.FRAME_RATE)
            EXPOSURE = configHashMap.get(CONFIG_KEY_NAME.EXPOSURE)
            SAVE_LIVE_IMG_PATH = configHashMap.get(CONFIG_KEY_NAME.SAVE_LIVE_IMG_PATH)
            UI_PATH = configHashMap.get(CONFIG_KEY_NAME.UI_PATH)
            INF_PATH = configHashMap.get(CONFIG_KEY_NAME.INF_PATH)
            RAW_IMG_PATH = configHashMap.get(CONFIG_KEY_NAME.RAW_IMG_PATH)

            for i, cam in enumerate(cam_list):
                node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
                device_serial_number = node_device_serial_number.GetValue()

                tlStreamSetup=cam.GetTLStreamNodeMap()
                resendFramesNode=PySpin.CBooleanPtr(tlStreamSetup.GetNode("StreamPacketResendEnable"))
                if PySpin.IsAvailable(resendFramesNode) and PySpin.IsReadable(resendFramesNode) and PySpin.IsWritable(resendFramesNode):
                    resendFramesNode.SetValue(False)

                deviceThroughput = PySpin.CIntegerPtr(cam.GetNodeMap().GetNode('DeviceLinkThroughputLimit'))

                if device_serial_number in [CAM_SERIAL_NO]:
                    if PySpin.IsAvailable(deviceThroughput) and PySpin.IsReadable(deviceThroughput):
                        # device_throughput = 34712000          #8312000+88000*10 #11927186. #
                        deviceThroughput.SetValue(DEVICE_THROUGHPUT_VALUE)
                
                AcquisitionFrameRateEnable=PySpin.CBooleanPtr(cam.GetNodeMap().GetNode("AcquisitionFrameRateEnabled"))
                if PySpin.IsAvailable(AcquisitionFrameRateEnable) and PySpin.IsReadable(AcquisitionFrameRateEnable) and PySpin.IsWritable(AcquisitionFrameRateEnable):
                    AcquisitionFrameRateEnable.SetValue(True)

                acquisition_frame_rate = PySpin.CFloatPtr(cam.GetNodeMap().GetNode("AcquisitionFrameRate"))
                if PySpin.IsAvailable(acquisition_frame_rate) and PySpin.IsWritable(acquisition_frame_rate):
                    acquisition_frame_rate.SetValue(FRAME_RATE)
                    print(f"FPS set to {FRAME_RATE} FPS")
                else:
                    print("Unable to set FPS.")
                
                configure_exposure(cam, EXPOSURE)
                # Set acquisition mode to continuous
                # node_acquisition_mode = PySpin.CEnumerationPtr(cam.GetNodeMap().GetNode('AcquisitionMode'))
                # if not PySpin.IsAvailable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
                #     logger.error(traceback.format_exc())
                #     return False

                # node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
                # if not PySpin.IsAvailable(node_acquisition_mode_continuous) or not PySpin.IsReadable(
                #         node_acquisition_mode_continuous):
                #     logger.error(traceback.format_exc())
                #     return False

                # acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()

                # node_acquisition_mode.SetIntValue(acquisition_mode_continuous)
                cam.BeginAcquisition()

            image_incomplete_counter = 0
            start_time = int(time.time())
            threshold_time = 600
            # Update the image capture loop
            while not self.stopThread:
                startTime = int(time.time() * 1000)
                try:
                    cycle_data = "/home/ultratech-tadipatri/insightzz/DPC-PROJECT/TempRawData/ContinousData/Right"
                    # TodaysDate = datetime.datetime.now().strftime('%Y_%m_%d')
                    if image_incomplete_counter >= 10:
                        image_incomplete_counter = 0
                    else:
                        for i, cam in enumerate(cam_list):
                            # grab_start = int(time.time() * 1000)
                            node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))

                            if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
                                device_serial_number = node_device_serial_number.GetValue()
                            
                            try:
                                image_result = cam.GetNextImage(1000)
                            except PySpin.SpinnakerException as ex:
                                print('Error: %s' % ex)
                                result = False
                                # cam.EndAcquisition()
                                continue

                            if image_result.IsIncomplete():
                                image_incomplete_counter = image_incomplete_counter + 1
                                print(device_serial_number)
                                # print('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
                                # print(traceback.format_exc())
                                logger.error(traceback.format_exc())
                                logger.error('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
                            else:
                                print(device_serial_number)
                                image_incomplete_counter = 0
                                image_data = image_result.GetNDArray()

                                image_data = cv2.cvtColor(image_data,cv2.COLOR_BayerRG2RGBA)
                                
                                # if device_serial_number in [SIDE1_CAM1_DEVICE,SIDE2_CAM2_DEVICE,SIDE3_CAM3_DEVICE]:
                                #     TodaysDate = datetime.datetime.now().strftime('%Y_%m_%d')             
                                #     if os.path.exists(os.path.join(SAVED_SITE_1_PATH, TodaysDate)) is False: 
                                #         os.mkdir(os.path.join(SAVED_SITE_1_PATH, TodaysDate))
                                #     if os.path.exists(os.path.join(os.path.join(SAVED_SITE_1_PATH, TodaysDate),device_serial_number)) is False:
                                #         os.mkdir(os.path.join(os.path.join(SAVED_SITE_1_PATH, TodaysDate),device_serial_number))

                                if device_serial_number == CAM_SERIAL_NO:
                                    img = image_data
                                    cv2.imwrite(f"{SAVE_LIVE_IMG_PATH}/IMG_1.jpg", img)
                                    if len(os.listdir(UI_PATH)) == 0:
                                        shutil.copy2(f"{SAVE_LIVE_IMG_PATH}/IMG_1.jpg", f"{UI_PATH}/IMG_1.jpg")
                                    
                                    if len(os.listdir(INF_PATH)) == 0:
                                        # pass
                                        shutil.copy2(f"{SAVE_LIVE_IMG_PATH}/IMG_1.jpg", f"{INF_PATH}/IMG_1.jpg")
                                    # shutil.copy2(f"{SAVE_LIVE_IMG_PATH}/IMG_1.jpg", f"{cycle_data}/{datetime.now().strftime('%Y_%m_%d_%H_%M_%S_%f')}.jpg")

                                    shutil.copy2(f"{SAVE_LIVE_IMG_PATH}/IMG_1.jpg", f"{RAW_IMG_PATH}/{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.jpg")
                                    # shutil.copy2(f"{SAVE_LIVE_IMG_PATH}/IMG_1.jpg", f"{cycle_data}/{datetime.now().strftime('%Y_%m_%d_%H_%M_%S_%f')}.jpg")
                                health_status = "OK"
                                current_time = int(time.time())
                                if current_time - start_time > threshold_time:
                                    self.updateHealthStatus(health_status, 0)
                                    start_time = int(time.time())
                                # for cam in cam_list:
                                image_result.Release()
                        
                        print(f"Total Time : {int(time.time() * 1000) - startTime}")
                except Exception as ex:
                    # print('Error: %s' % ex)
                    tb = traceback.format_exc()

                    # Extracting detailed information
                    exception_message = str(ex)
                    last_traceback = traceback.extract_tb(ex.__traceback__)[-1]  # Get the last traceback frame
                    function_name = last_traceback.name
                    line_number = last_traceback.lineno
                    filename = last_traceback.filename

                    # Combine information into a detailed error message
                    detailed_error_message = (f"Error occurred in function '{function_name}' in {filename}, "
                                            f"at line {line_number}: {exception_message}\n\nTraceback:\n{tb}")
                    result = False
                    health_status = "NOK"
                    current_time = int(time.time())
                    if current_time - start_time > threshold_time:
                        self.updateHealthStatus(health_status, 0)
                        start_time = int(time.time())
                    # mail_sender = CameraMailSender()
                    # mail_sender.send_camera_error_email(detailed_error_message, CameraName)

            for cam in cam_list:
                cam.EndAcquisition()
        except PySpin.SpinnakerException as ex:
            # Capture the traceback
            tb = traceback.format_exc()
            # Extracting detailed information
            exception_message = str(ex)
            last_traceback = traceback.extract_tb(ex.__traceback__)[-1]  # Get the last traceback frame
            function_name = last_traceback.name
            line_number = last_traceback.lineno
            filename = last_traceback.filename

            detailed_error_message = (f"Error occurred in function '{function_name}' in {filename}, "
                                    f"at line {line_number}: {exception_message}\n\nTraceback:\n{tb}")
            logger.error(detailed_error_message)
            # email_sender = CameraMailSender()
            # email_sender.send_camera_error_email(detailed_error_message, CameraName)
            result = False

        return result
    
    def hexToIP(self, hex_address):
        # Hexadecimal representation
        # hex_address = "0xc0a80202"
        # Remove the '0x' prefix and convert to an integer
        int_address = int(hex_address, 16)

        # Convert the integer to IPv4 notation
        ip_address = ".".join(map(str, [(int_address >> 24) & 0xFF, (int_address >> 16) & 0xFF, (int_address >> 8) & 0xFF, int_address & 0xFF]))

        # Print the IPv4 address
        print("IPv4 Address:", ip_address)

        return ip_address


    # def print_device_info(self,nodemap, cam_num):
    #     try:
    #         result = True
    #         node_device_information = PySpin.CCategoryPtr(nodemap.GetNode('DeviceInformation'))

    #         if PySpin.IsAvailable(node_device_information) and PySpin.IsReadable(node_device_information):
    #             features = node_device_information.GetFeatures()
    #             for feature in features:
    #                 node_feature = PySpin.CValuePtr(feature)
    #                 if "GevDeviceIPAddress" == node_feature.GetName():
    #                     ip = self.hexToIP(node_feature.ToString())
    #                     print(ip)
    #                 print('%s: %s' % (node_feature.GetName(),
    #                                 node_feature.ToString() if PySpin.IsReadable(node_feature) else 'Node not readable'))

    #         else:
    #             logger.error(traceback.format_exc())

    #     except PySpin.SpinnakerException as ex:
    #         # logger.error(traceback.format_exc())
    #         tb = traceback.format_exc()
    #         # Extracting detailed information
    #         exception_message = str(ex)
    #         last_traceback = traceback.extract_tb(ex.__traceback__)[-1]  # Get the last traceback frame
    #         function_name = last_traceback.name
    #         line_number = last_traceback.lineno
    #         filename = last_traceback.filename

    #         # Combine information into a detailed error message
    #         detailed_error_message = (f"Error occurred in function '{function_name}' in {filename}, "
    #                                 f"at line {line_number}: {exception_message}\n\nTraceback:\n{tb}")
    #         logger.error(detailed_error_message)
    #         # email_sender = CameraMailSender()
    #         # email_sender.send_camera_error_email(detailed_error_message, CameraName)
    #         return False

    #     return result

    def getSerialNumber(self,cam):
        device_serial_number = ''
        nodemap_tldevice = cam.GetTLDeviceNodeMap()
        node_device_serial_number = PySpin.CStringPtr(nodemap_tldevice.GetNode('DeviceSerialNumber'))
        if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
            device_serial_number = node_device_serial_number.GetValue()
        return device_serial_number   

    def run_multiple_cameras(self, cam_list):
        try:
            result = True
            for i, cam in enumerate(cam_list):
                cam.Init()

            result &= self.acquire_images(cam_list)

            for cam in cam_list:
                cam.DeInit()

            del cam

        except PySpin.SpinnakerException as ex:
            tb = traceback.format_exc()
            # Extracting detailed information
            exception_message = str(ex)
            last_traceback = traceback.extract_tb(ex.__traceback__)[-1]  # Get the last traceback frame
            function_name = last_traceback.name
            line_number = last_traceback.lineno
            filename = last_traceback.filename

            # Combine information into a detailed error message
            detailed_error_message = (f"Error occurred in function '{function_name}' in {filename}, "
                                    f"at line {line_number}: {exception_message}\n\nTraceback:\n{tb}")
            # logger.error(detailed_error_message)
            # email_sender = CameraMailSender()
            # email_sender.send_camera_error_email(detailed_error_message, CameraName)
            # logger.error(traceback.format_exc())
            print('Error: %s' % ex)
            result = False

        return result

    def get_camera_host_and_port(self, camera):
        try:
            # Get the transport layer node map (TLDevice, TLStream, etc.)
            transport_layer_nodemap = camera.GetTLDeviceNodeMap()

            # Get the device's IP address
            device_ip_node = PySpin.CStringPtr(transport_layer_nodemap.GetNode('GevDeviceIPAddress'))
            if PySpin.IsAvailable(device_ip_node) and PySpin.IsReadable(device_ip_node):
                host = device_ip_node.GetValue()
                print(f'Camera IP address (host): {host}')

            # Get the device's port number
            device_port_node = PySpin.CIntegerPtr(transport_layer_nodemap.GetNode('GevDevicePort'))
            if PySpin.IsAvailable(device_port_node) and PySpin.IsReadable(device_port_node):
                port = device_port_node.GetValue()
                print(f'Camera port number: {port}')

        except PySpin.SpinnakerException as e:
            print(f'Error: {e}')

    def query_interface(self, interface, interfaceName, deviceList):
        required_cam_list = []
        try:
            node_interface_display_name = interface.TLInterface.InterfaceDisplayName
            if PySpin.IsAvailable(node_interface_display_name) and PySpin.IsReadable(node_interface_display_name):
                interface_display_name = node_interface_display_name.GetValue()
                print(interface_display_name)
            else:
                print("Interface display name not readable")

            if interfaceName != interface_display_name:
                return required_cam_list

            interface.UpdateCameras()
            cam_list = interface.GetCameras()
            num_cams = cam_list.GetSize()

            if num_cams == 0:
                print("\tNo devices detected.\n")
                return required_cam_list
            
            for i in range(num_cams):
                cam = cam_list[i]
                deviceId = self.getSerialNumber(cam)
                if deviceId in deviceList:
                    print(f"Camera ID Added is {deviceId}")
                    required_cam_list.append(cam)

            cam_list.Clear()

        except PySpin.SpinnakerException as ex:
            print("query_interface() Error: %s" % ex)
            
        return required_cam_list

    def initCam(self):
        result = True

        system = PySpin.System.GetInstance()
        
        cam_list = system.GetCameras()
        interface_list = system.GetInterfaces()
        num_interfaces = interface_list.GetSize()
        num_cameras = cam_list.GetSize()

        if num_cameras == 0:
            cam_list.Clear()
            system.ReleaseInstance()
            logger.error(traceback.format_exc())
            return False
        
        # interfaceName = "GEV Interface 1"
        interfaceName = configHashMap.get(CONFIG_KEY_NAME.INTERFACE_NAME)
        CAM_SERIAL_NO = configHashMap.get(CONFIG_KEY_NAME.CAM_SERIAL_NO)
        deviceList = [CAM_SERIAL_NO]
        new_cam_list = None
        for i in range(num_interfaces):
            interface = interface_list[i]
            new_cam_list = self.query_interface(interface, interfaceName, deviceList)
            if len(new_cam_list) > 0:
                break

        # Release interface
        del interface
        
        result = self.run_multiple_cameras(new_cam_list)

        print('Camera Script Closing ')

        cam_list.Clear()
        system.ReleaseInstance()

        return result

def updateProcessID():
    dbConn = None
    cur = None
    try:
        dbConn = getDatabaseConnection()
        cur = dbConn.cursor()
        query = f"update PROCESS_ID_TABLE set PROCESS_ID='{PROCESS_ID}' where PROCESS_NAME ='FRAME_CAPTURE'"
        cur.execute(query)
        dbConn.commit()

    except Exception as e:
        logger.critical("updateProcessID() Exception is : "+ str(e))
    
    finally:
        cur.close()
        dbConn.close()

# Call create_directories before initializing the FlirCam object
#updateProcessID()
if __name__ == "__main__":
    loadConfiguration()
    initializeLogger()
    FlirCam()