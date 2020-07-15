from queue import Queue
import cv2
from PyQt5.QtCore import (QThread, QTime, QMutex, pyqtSignal, QMutexLocker)

from .structures import ThreadStatisticsData


class BaseThread(QThread):

    """
    Base class for all types of threads (capture, processing, stitching, ...,
    etc). Mainly for collecting statistics of the threads.
    """

    FPS_STAT_QUEUE_LENGTH = 32

    update_statistics_gui = pyqtSignal(ThreadStatisticsData)

    def __init__(self, parent=None):
        super(BaseThread, self).__init__(parent)
        self.init_commons()

    def init_commons(self):
        self.stopped = False
        self.stop_mutex = QMutex()
        self.clock = QTime()
        self.fps = Queue()
        self.processing_time = 0
        self.processing_mutex = QMutex()
        self.fps_sum = 0
        self.stat_data = ThreadStatisticsData()

    def stop(self):
        with QMutexLocker(self.stop_mutex):
            self.stopped = True

    def update_fps(self, dt):
        # add instantaneous fps value to queue
        if dt > 0:
            self.fps.put(1000 / dt)

        # discard redundant items in the fps queue
        if self.fps.qsize() > self.FPS_STAT_QUEUE_LENGTH:
            self.fps.get()

        # update statistics
        if self.fps.qsize() == self.FPS_STAT_QUEUE_LENGTH:
            while not self.fps.empty():
                self.fps_sum += self.fps.get()

            self.stat_data.average_fps = round(self.fps_sum / self.FPS_STAT_QUEUE_LENGTH, 2)
            self.fps_sum = 0
