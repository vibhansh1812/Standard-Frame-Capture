FRAME CAPTURE FA
Now first we taking the mahindra FA in whicch we use FLIR Camera 
1. This module helps in capturing images from multiple FLIR cameras using the Spinnaker SDK.
2. It works with both a database and the computer’s storage to manage everything.
3. Set up cameras so they are ready to take pictures.
4. Take dummy images first (to warm up the cameras).
5. Capture real images whenever the database tells it to start.
6. Save images in folders organized by VIN numbers.
7. Update the database about the camera’s status and progress

   
File Responsibilities
CAMERA HANDLING
1. The code starts multiple FLIR cameras using their unique serial numbers.
2. It sets camera settings like brightness, exposure time, framerate, buffer, and image format.
3. It then takes pictures and saves them as JPEG files.
Each camera is configured with parameters like:
1. Brightness (via exposure control).
2. Exposure time (set manually, auto exposure turned off).
3. Frame rate (ensures stable capture, ~1 fps).
4. Buffer settings (set to “NewestOnly” with manual buffer size = 100).
5. Pixel format (Bayer → BGR conversion).
10. Device throughput (~6500000 per camera, adjusted within allowed range).
IMAGE CAPTURE
1. When a trigger is received (VIN number from the database), each camera captures an image.
2. Multiple attempts (up to 5) are made per camera if errors occur.
3. After capture, the code checks whether the image is complete (not corrupted).
4. If incomplete, it logs an error
5. Valid images are converted to BGR8 format (for OpenCV compatibility).
This way your team can see the end-to-end flow:
Init → Config → Dummy Test → Capture → Validate → Save → Verify → Log → Cleanup
DATABASE INTERACTION
1. The code checks the database to see if it should start capturing images.
2. It updates the database to show if the cameras are healthy (working fine).
3. It also marks in the database when image capturing is finished.
FILE I/O
1. Store images in paths defined by configuration (config_one.xml).
2. Maintain trigger files for UI/inference pipelines.
LOGGING
The code keeps daily logs (separate files for each day).
Logs include:
1. Which configuration was loaded.
2. When images were captured.
3. Any errors that happened.

FUNCTIONS ARE TO BE MENTIONED IN THIS CODE ARE :- 
loadConfiguration() – Load paths and DB configs.
getDatabaseConnection() – Establish DB connection.
initializeLogger() – Setup logging.
configureMVCameraFlir() – Configure individual FLIR cameras.
mainFunction() – Core loop:


FLOWCHART FOR FA 
 ┌─────────────────────────┐
 │   Program Start (main)  │
 └───────────┬─────────────┘
             │
             ▼
 ┌─────────────────────────┐
 │ loadConfiguration()     │
 │ → Parse XML config file │
 │ → Fill configHashMap    │
 └───────────┬─────────────┘
             │
             ▼
 ┌─────────────────────────┐
 │ initializeLogger()      │
 │ → Setup rotating logs   │
 └───────────┬─────────────┘
             │
             ▼
 ┌─────────────────────────┐
 │ Infinite Loop (while)   │
 └───────────┬─────────────┘
             │
             ▼
 ┌─────────────────────────┐
 │ mainFunction()          │
 └───────────┬─────────────┘
             │
             ▼
 ┌─────────────────────────────────────┐
 │ update_init_status("ACTIVE")        │
 │ Create INIT_CAPTURE folder          │
 │ Initialize FLIR system + cameras    │
 │ Filter cameras (ALL_DEVICES list)   │
 └───────────┬────────────────────────┘
             │
             ▼
 ┌─────────────────────────┐
 │ Configure Cameras        │
 │ (configureMVCameraFlir) │
 │ → Exposure, FrameRate,  │
 │   Buffer, PixelFormat   │
 └───────────┬─────────────┘
             │
             ▼
 ┌─────────────────────────┐
 │ Dummy Capture            │
 │ → Capture INIT images    │
 │   Save to INIT_CAPTURE   │
 └───────────┬─────────────┘
             │
             ▼
 ┌─────────────────────────────────┐
 │ update_init_status("INACTIVE")  │
 │ Enter Capture Loop              │
 └───────────┬────────────────────┘
             │
             ▼
 ┌─────────────────────────┐
 │ fetchtrigger()          │
 │ → Check DB for trigger  │
 │   (framecapture, VIN)   │
 └───────────┬─────────────┘
             │
    ┌────────┴───────────┐
    │ VIN Ready & New?    │─────────────No───────────┐
    │ (start==1 & VIN OK) │                           │
    └─────────┬───────────┘                           │
              │Yes                                     │
              ▼                                        │
 ┌─────────────────────────┐                          │
 │ Create VIN folder        │                          │
 │ Capture Images           │                          │
 │ → For each camera        │                          │
 │   Try up to 5 attempts   │                          │
 │   Save IMG_xx.jpeg       │                          │
 └───────────┬─────────────┘                          │
             │                                        │
             ▼                                        │
 ┌─────────────────────────┐                          │
 │ If all 13 images saved  │                          │
 │ → Update triggers in DB │                          │
 │ → Write VIN to trigger  │                          │
 │   files (UI + System)   │                          │
 │ → updateAllTriggerStatus│                          │
 └───────────┬─────────────┘                          │
             │                                        │
             ▼                                        │
 ┌─────────────────────────┐                          │
 │ Update last_capture time │                          │
 │ Set previous_vin_number  │                          │
 └───────────┬─────────────┘                          │
             │                                        │
             ▼                                        │
 ┌───────────────────────────────────────────────┐
 │ Exit Conditions:                              │
 │ - Current time between 6:10–6:15 AM           │
 │ - No capture for more than 1 hour             │
 └─────────────────┬─────────────────────────────┘
                   │
                   ▼
 ┌─────────────────────────┐
 │ Release all cameras      │
 │ → EndAcquisition, DeInit │
 │ → Release FlirSystem     │
 │ → gc.collect()           │
 └───────────┬─────────────┘
             │
             ▼
 ┌─────────────────────────┐
 │ Loop Back to mainFunction│
 └─────────────────────────┘
