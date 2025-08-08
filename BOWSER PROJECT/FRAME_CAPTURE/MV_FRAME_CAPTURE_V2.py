
import os
import PySpin
import sys
import time
import cv2
import threading
import datetime
import shutil
import logging
import pymysql

logger = None
log_format=logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger=logging.getLogger("/home/bowaser-inspection/INSIGHTZZ/CODE/FRAME_CAPTURE/LOGS/MV.log")
logger.setLevel(logging.DEBUG)
logger_fh=logging.FileHandler("/home/bowaser-inspection/INSIGHTZZ/CODE/FRAME_CAPTURE/LOGS/MV.log",mode='a')
logger_fh.setFormatter(log_format)
logger_fh.setLevel(logging.DEBUG)
logger.addHandler(logger_fh)
logger.debug("MV started")

''' DB credentials '''
db_host="localhost"
db_user="root"
db_pass="insightzz@123"
db_name="BOWSER_INSPECTION_DB"

SAVED_DATA_PATH="/home/bowaser-inspection/INSIGHTZZ/CODE/ALGORITHM/SAVED_DATA"
START_TRIGGER="/home/bowaser-inspection/INSIGHTZZ/CODE/ALGORITHM/TRIGGERS/START/start.txt"
STOP_TRIGGER="/home/bowaser-inspection/INSIGHTZZ/CODE/ALGORITHM/TRIGGERS/STOP/stop.txt"
LIVE_IMG = "/home/bowaser-inspection/INSIGHTZZ/CODE/ALGORITHM/SAVED_DATA/LIVE/TMP.jpg"
TMP_LIVE_IMG = "/home/bowaser-inspection/INSIGHTZZ/CODE/ALGORITHM/SAVED_DATA/LIVE/TMP/TMP.jpg"

PROCESS_ID = os.getpid()

class BufferlessCapture():
    def __init__(self, thread_lock):
        self.Grab=False
        self.Frame=None
        self.stopFlag=False
        self.thread_lock = thread_lock
        # self.updateProcessID()
        t1=threading.Thread(target=self.initCam)
        t1.start()

    def updateProcessID(self):
        try:
            db_update = self.getting_dB_connection()
            cur = db_update.cursor()
            query = f"update PROCESS_ID_TABLE set PROCESS_ID='{PROCESS_ID}' where PROCESS_NAME ='FRAME_CAPTURE'"
            cur.execute(query)
            db_update.commit()
        except Exception as e:
            logger.critical("updateProcessID() Exception is : "+ str(e))
        finally:
            cur.close()
            db_update.close()
    
    def getting_dB_connection(self):
        db_conn=None
        try:
            db_conn=pymysql.connect(host=db_host,user=db_user,password=db_pass,db=db_name)
        except Exception as e:
            logger.critical(f'getting_dB_connection() Exception : {e}')
        return db_conn
    
    def acquire_and_display_images(self,cam, nodemap, nodemap_tldevice):
        counter=100000

        sNodemap = cam.GetTLStreamNodeMap()

        # Change bufferhandling mode to NewestOnly
        node_bufferhandling_mode = PySpin.CEnumerationPtr(sNodemap.GetNode('StreamBufferHandlingMode'))
        if not PySpin.IsAvailable(node_bufferhandling_mode) or not PySpin.IsWritable(node_bufferhandling_mode):
            print('Unable to set stream buffer handling mode.. Aborting...')
            return False

        deviceThroughput=PySpin.CIntegerPtr(sNodemap.GetNode('DeviceLinkThroughputLimit'))

        if PySpin.IsAvailable(deviceThroughput) and PySpin.IsReadable(deviceThroughput):
            device_throughput = 8312000+88000*10 #11927186. #
            deviceThroughput.SetValue(device_throughput)

        # Retrieve entry node from enumeration node
        node_newestonly = node_bufferhandling_mode.GetEntryByName('NewestOnly')
        if not PySpin.IsAvailable(node_newestonly) or not PySpin.IsReadable(node_newestonly):
            print('Unable to set stream buffer handling mode.. Aborting...')
            return False

        # Retrieve integer value from entry node
        node_newestonly_mode = node_newestonly.GetValue()

        # Set integer value from entry node as new value of enumeration node
        node_bufferhandling_mode.SetIntValue(node_newestonly_mode)

        print('*** IMAGE ACQUISITION ***\n')
        try:
            
            node_acquisition_mode = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionMode'))
            if not PySpin.IsAvailable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
                print('Unable to set acquisition mode to continuous (enum retrieval). Aborting...')
                return False

            # Retrieve entry node from enumeration node
            node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
            if not PySpin.IsAvailable(node_acquisition_mode_continuous) or not PySpin.IsReadable(
                    node_acquisition_mode_continuous):
                print('Unable to set acquisition mode to continuous (entry retrieval). Aborting...')
                return False

            # Retrieve integer value from entry node
            acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()

            # Set integer value from entry node as new value of enumeration node
            node_acquisition_mode.SetIntValue(acquisition_mode_continuous)

            print('Acquisition mode set to continuous...')
            cam.BeginAcquisition()
            print('Acquiring images...')
            device_serial_number = ''
            node_device_serial_number = PySpin.CStringPtr(nodemap_tldevice.GetNode('DeviceSerialNumber'))
            if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
                device_serial_number = node_device_serial_number.GetValue()
                print('Device serial number retrieved as %s...' % device_serial_number)
            print('Press enter to close the program..')
            self.Grab=False
            prev_time=0
            captured=False
            try:
                os.remove(STOP_TRIGGER)
                logger.debug("Stop Trigger File Found, Removing the file to start the process")
            except:
                pass
            while self.stopFlag is False:
                if os.path.exists(STOP_TRIGGER):
                    logger.debug("Stop Trigger file has been created to stop the process")
                    try:
                        os.remove(START_TRIGGER)
                        logger.debug("Removing Start File")
                    except:
                        pass
                    try:
                        os.remove(STOP_TRIGGER)
                        logger.debug("Removing Stop File")
                    except:
                        pass
                    try:
                        os.remove(LIVE_IMG)
                        logger.debug("Removing Stop File")
                    except:
                        pass
                    try:
                        os.remove(TMP_LIVE_IMG)
                        logger.debug("Removing Stop File")
                    except:
                        pass
                    break

                if os.path.exists(START_TRIGGER) and self.Grab==False:
                    fd=open(START_TRIGGER)
                    logger.debug("Start Trigger file exists")
                    line=fd.readline()
                    print(line)
                    line=line.replace("\n","")
                    print(line)
                    BOWSER_NUMBER=''
                    
                    if line=='':
                        BOWSER_NUMBER=str(int(time.time())*1000)
                        HOLE_NUMBER=0
                    else:
                        BOWSER_NUMBER=line.split("_")[0]
                        HOLE_NUMBER=line.split("_")[1]
                    
                    logger.debug("Start Trigger file exists and Bowser no is : "+str(BOWSER_NUMBER))

                    if not os.path.exists(SAVED_DATA_PATH+'/'+str(BOWSER_NUMBER)):
                        os.mkdir(SAVED_DATA_PATH+'/'+str(BOWSER_NUMBER))
                    if not os.path.exists(SAVED_DATA_PATH+'/'+str(BOWSER_NUMBER)+"/"+str(HOLE_NUMBER)):
                        os.mkdir(SAVED_DATA_PATH+'/'+str(BOWSER_NUMBER)+"/"+str(HOLE_NUMBER))
                    
                    self.Grab=True
                    counter=100000
                try:
                    image_result = cam.GetNextImage(1000)
                    if image_result.IsIncomplete():
                        print('Image incomplete with image status %d ...' % image_result.GetImageStatus())
                    else:                    
                        if self.Grab:
                            if captured:
                                if int(time.time())*1000-prev_time>500:
                                    captured=False
                            else:
                                counter=counter+1
                                if counter > 100005:
                                    image_data = image_result.GetNDArray()
                                    image_data=cv2.cvtColor(image_data,cv2.COLOR_BayerRG2RGBA)
                                    filepath=f"{SAVED_DATA_PATH}/{BOWSER_NUMBER}/{HOLE_NUMBER}/IMG_{counter}.jpg"
                                    image_data=cv2.rotate(image_data,cv2.ROTATE_180)
                                    cv2.imwrite(filepath,image_data)

                                    try:
                                        shutil.copy2(filepath, LIVE_IMG)
                                        shutil.copy2(filepath, TMP_LIVE_IMG)
                                    except Exception as e:
                                        print(f"Exception in saving File {LIVE_IMG}, {TMP_LIVE_IMG}")
                                
                                    prev_time=int(time.time())*1000
                                    captured=True
                        else:
                            self.Frame=None
                            image_data = image_result.GetNDArray()
                            image_data=cv2.cvtColor(image_data,cv2.COLOR_BayerRG2RGBA)
                            cv2.imwrite(TMP_LIVE_IMG,image_data)
                            try:
                                os.remove(LIVE_IMG)
                            except:
                                pass
                    
                    image_result.Release()

                except PySpin.SpinnakerException as ex:
                    print('Error: %s' % ex)
                    return False

            cam.EndAcquisition()

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            return False

        return True

    def handle_close(self,evt):
        """
        This function will close the GUI when close event happens.

        :param evt: Event that occurs when the figure closes.
        :type evt: Event
        """
        continue_recording = False

    def run_single_camera(self,cam):
        """
        This function acts as the body of the example; please see NodeMapInfo example
        for more in-depth comments on setting up cameras.

        :param cam: Camera to run on.
        :type cam: CameraPtr
        :return: True if successful, False otherwise.
        :rtype: bool
        """
        try:
            result = True

            nodemap_tldevice = cam.GetTLDeviceNodeMap()

            # Initialize camera
            cam.Init()

            # Retrieve GenICam nodemap
            nodemap = cam.GetNodeMap()

            # Acquire images
            result &= self.acquire_and_display_images(cam, nodemap, nodemap_tldevice)

            # Deinitialize camera
            cam.DeInit()

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            result = False

        return result


    def initCam(self):
        """
        Example entry point; notice the volume of data that the logging event handler
        prints out on debug despite the fact that very little really happens in this
        example. Because of this, it may be better to have the logger set to lower
        level in order to provide a more concise, focused log.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        result = True

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

        # Run example on each camera
        for i, cam in enumerate(cam_list):

            print('Running example for camera %d...' % i)

            result &= self.run_single_camera(cam)
            print('Camera %d example complete... \n' % i)

        # Release reference to camera
        # NOTE: Unlike the C++ examples, we cannot rely on pointer objects being automatically
        # cleaned up when going out of scope.
        # The usage of del is preferred to assigning the variable to None.
        del cam

        # Clear camera list before releasing system
        cam_list.Clear()

        # Release system instance
        try:
            system.ReleaseInstance()
        except:
            print("camera Error")
        
        return result
thread_lock = threading.Lock() 
obj=BufferlessCapture(thread_lock)


