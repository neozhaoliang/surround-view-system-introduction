import cv2
from PyQt5.QtCore import qDebug

from .base_thread import BaseThread
from .structures import ImageFrame
from .utils import gstreamer_pipeline


class CaptureThread(BaseThread):

    def __init__(self,
                 device_id,
                 flip_method=2,
                 drop_if_full=True,
                 api_preference=cv2.CAP_GSTREAMER,
                 resolution=None,
                 use_gst=True,
                 parent=None):
        """
        device_id: device number of the camera.
        flip_method: 0 for identity, 2 for 180 degree rotation (if the camera is installed
            up-side-down).
        drop_if_full: drop the frame if buffer is full.
        api_preference: cv2.CAP_GSTREAMER for csi cameras, usually cv2.CAP_ANY would suffice.
        resolution: camera resolution (width, height).
        """
        super(CaptureThread, self).__init__(parent)
        self.device_id = device_id
        self.flip_method = flip_method
        self.use_gst = use_gst
        self.drop_if_full = drop_if_full
        self.api_preference = api_preference
        self.resolution = resolution
        self.cap = cv2.VideoCapture()
        # an instance of the MultiBufferManager object,
        # for synchronizing this thread with other cameras.
        self.buffer_manager = None

    def run(self):
        if self.buffer_manager is None:
            raise ValueError("This thread has not been binded to any buffer manager yet")

        while True:
            self.stop_mutex.lock()
            if self.stopped:
                self.stopped = False
                self.stop_mutex.unlock()
                break
            self.stop_mutex.unlock()

            # save capture time
            self.processing_time = self.clock.elapsed()
            # start timer (used to calculate capture rate)
            self.clock.start()

            # synchronize with other streams (if enabled for this stream)
            self.buffer_manager.sync(self.device_id)

            if not self.cap.grab():
                continue

            # retrieve frame and add it to buffer
            _, frame = self.cap.retrieve()
            img_frame = ImageFrame(self.clock.msecsSinceStartOfDay(), frame)
            self.buffer_manager.get_device(self.device_id).add(img_frame, self.drop_if_full)

            # update statistics
            self.update_fps(self.processing_time)
            self.stat_data.frames_processed_count += 1
            # inform GUI of updated statistics
            self.update_statistics_gui.emit(self.stat_data)

        qDebug("Stopping capture thread...")

    def connect_camera(self):
        if self.use_gst:
            options = gstreamer_pipeline(cam_id=self.device_id, flip_method=self.flip_method)
            self.cap.open(options, self.api_preference)
        else:
            self.cap.open(self.device_id)
        # return false if failed to open camera
        if not self.cap.isOpened():
            qDebug("Cannot open camera {}".format(self.device_id))
            return False
        else:
            # try to set camera resolution
            if self.resolution is not None:
                width, height = self.resolution
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                # some camera may become closed if the resolution is not supported
                if not self.cap.isOpened():
                    qDebug("Resolution not supported by camera device: {}".format(self.resolution))
                    return False
            # use the default resolution
            else:
                width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.resolution = (width, height)

        return True

    def disconnect_camera(self):
        # disconnect camera if it's already opened.
        if self.cap.isOpened():
            self.cap.release()
            return True
        # else do nothing and return
        else:
            return False

    def is_camera_connected(self):
        return self.cap.isOpened()
