from PyQt5.QtCore import QSemaphore, QMutex, QMutexLocker, QWaitCondition
from queue import Queue
import numpy as np
from .param_settings import project_shapes


class Buffer(object):

    def __init__(self, buffer_size=5):
        self.buffer_size = buffer_size
        self.free_slots = QSemaphore(self.buffer_size)
        self.used_slots = QSemaphore(0)
        self.clear_buffer_add = QSemaphore(1)
        self.clear_buffer_get = QSemaphore(1)
        self.queue_mutex = QMutex()
        self.queue = Queue(self.buffer_size)

    def add(self, data, drop_if_full=False):
        self.clear_buffer_add.acquire()
        if drop_if_full:
            if self.free_slots.tryAcquire():
                self.queue_mutex.lock()
                self.queue.put(data)
                self.queue_mutex.unlock()
                self.used_slots.release()
        else:
            self.free_slots.acquire()
            self.queue_mutex.lock()
            self.queue.put(data)
            self.queue_mutex.unlock()
            self.used_slots.release()

        self.clear_buffer_add.release()

    def get(self):
        # acquire semaphores
        self.clear_buffer_get.acquire()
        self.used_slots.acquire()
        self.queue_mutex.lock()
        data = self.queue.get()
        self.queue_mutex.unlock()
        # release semaphores
        self.free_slots.release()
        self.clear_buffer_get.release()
        # return item to caller
        return data

    def clear(self):
        # check if buffer contains items
        if self.queue.qsize() > 0:
            # stop adding items to buffer (will return false if an item is currently being added to the buffer)
            if self.clear_buffer_add.tryAcquire():
                # stop taking items from buffer (will return false if an item is currently being taken from the buffer)
                if self.clear_buffer_get.tryAcquire():
                    # release all remaining slots in queue
                    self.free_slots.release(self.queue.qsize())
                    # acquire all queue slots
                    self.free_slots.acquire(self.buffer_size)
                    # reset used_slots to zero
                    self.used_slots.acquire(self.queue.qsize())
                    # clear buffer
                    for _ in range(self.queue.qsize()):
                        self.queue.get()
                    # release all slots
                    self.free_slots.release(self.buffer_size)
                    # allow get method to resume
                    self.clear_buffer_get.release()
                else:
                    return False
                # allow add method to resume
                self.clear_buffer_add.release()
                return True
            else:
                return False
        else:
            return False

    def size(self):
        return self.queue.qsize()

    def maxsize(self):
        return self.buffer_size

    def isfull(self):
        return self.queue.qsize() == self.buffer_size

    def isempty(self):
        return self.queue.qsize() == 0


class MultiBufferManager(object):

    """
    Class for synchronizing capture threads from different cameras.
    """

    def __init__(self, do_sync=True):
        self.sync_devices = set()
        self.do_sync = do_sync
        self.wc = QWaitCondition()
        self.mutex = QMutex()
        self.arrived = 0
        self.buffer_maps = dict()

    def bind_thread(self, thread, buffer_size, sync=True):
        self.create_buffer_for_device(thread.device_id, buffer_size, sync)
        thread.buffer_manager = self

    def create_buffer_for_device(self, device_id, buffer_size, sync=True):
        if sync:
            with QMutexLocker(self.mutex):
                self.sync_devices.add(device_id)

        self.buffer_maps[device_id] = Buffer(buffer_size)

    def get_device(self, device_id):
        return self.buffer_maps[device_id]

    def remove_device(self, device_id):
        self.buffer_maps.pop(device_id)
        with QMutexLocker(self.mutex):
            if device_id in self.sync_devices:
                self.sync_devices.remove(device_id)
                self.wc.wakeAll()

    def sync(self, device_id):
        # only perform sync if enabled for specified device/stream
        self.mutex.lock()
        if device_id in self.sync_devices:
            # increment arrived count
            self.arrived += 1
            # we are the last to arrive: wake all waiting threads
            if self.do_sync and self.arrived == len(self.sync_devices):
                self.wc.wakeAll()
            # still waiting for other streams to arrive: wait
            else:
                self.wc.wait(self.mutex)
            # decrement arrived count
            self.arrived -= 1
        self.mutex.unlock()

    def wake_all(self):
        with QMutexLocker(self.mutex):
            self.wc.wakeAll()

    def set_sync(self, enable):
        self.do_sync = enable

    def sync_enabled(self):
        return self.do_sync

    def sync_enabled_for_device(self, device_id):
        return device_id in self.sync_devices

    def __contains__(self, device_id):
        return device_id in self.buffer_maps

    def __str__(self):
        return (self.__class__.__name__ + ":\n" + \
                "sync: {}\n".format(self.do_sync) + \
                "devices: {}\n".format(tuple(self.buffer_maps.keys())) + \
                "sync enabled devices: {}".format(self.sync_devices))


class ProjectedImageBuffer(object):

    """
    Class for synchronizing processing threads from different cameras.
    """

    def __init__(self, drop_if_full=True, buffer_size=8):
        self.sync_devices = set()
        self.buffer = Buffer(buffer_size)
        self.drop_if_full = drop_if_full
        self.wc = QWaitCondition()
        self.mutex = QMutex()
        self.arrived = 0
        self.current_frames = dict()

    def bind_thread(self, thread):
        with QMutexLocker(self.mutex):
            self.sync_devices.add(thread.device_id)

        shape = project_shapes[thread.camera_model.camera_name]
        self.current_frames[thread.device_id] = np.zeros(shape[::-1] + (3,), np.uint8)
        thread.proc_buffer_manager = self

    def get(self):
        return self.buffer.get()

    def set_frame_for_device(self, device_id, frame):
        if device_id not in self.sync_devices:
            raise ValueError("Device not held by the buffer: {}".format(device_id))
        self.current_frames[device_id] = frame

    def sync(self, device_id):
        # only perform sync if enabled for specified device/stream
        self.mutex.lock()
        if device_id in self.sync_devices:
            # increment arrived count
            self.arrived += 1
            # we are the last to arrive: wake all waiting threads
            if self.arrived == len(self.sync_devices):
                self.buffer.add(self.current_frames, self.drop_if_full)
                self.wc.wakeAll()
            # still waiting for other streams to arrive: wait
            else:
                self.wc.wait(self.mutex)
            # decrement arrived count
            self.arrived -= 1
        self.mutex.unlock()

    def wake_all(self):
        with QMutexLocker(self.mutex):
            self.wc.wakeAll()

    def __contains__(self, device_id):
        return device_id in self.sync_devices

    def __str__(self):
        return (self.__class__.__name__ + ":\n" + \
                "devices: {}\n".format(self.sync_devices))
