import numpy as np
import cv2
import os
from PyQt5.QtCore import QMutex
from .base_thread import BaseThread
from .buffer import Buffer
from .param_settings import *
from .utils import *


def FI(front_image):
    return front_image[:, :xl]


def FII(front_image):
    return front_image[:, xr:]


def FM(front_image):
    return front_image[:, xl:xr]


def BIII(back_image):
    return back_image[:, :xl]


def BIV(back_image):
    return back_image[:, xr:]


def BM(back_image):
    return back_image[:, xl:xr]


def LI(left_image):
    return left_image[:yt, :]


def LIII(left_image):
    return left_image[yb:, :]


def LM(left_image):
    return left_image[yt:yb, :]


def RII(right_image):
    return right_image[:yt, :]


def RIV(right_image):
    return right_image[yb:, :]


def RM(right_image):
    return right_image[yt:yb, :]


class BirdView(BaseThread):

    def __init__(self,
                 receive_buffer_manager=None,
                 drop_if_full=True,
                 buffer_size=8,
                 parent=None):
        super(BirdView, self).__init__(parent)
        self.image = np.zeros((total_h, total_w, 3), np.uint8)
        self.weights = None
        self.receive_buffer_manager = receive_buffer_manager
        self.drop_if_full = drop_if_full
        self.buffer = Buffer(buffer_size)
        self.car_image = cv2.imread(os.path.join(os.getcwd(), "images", "car.png"))
        self.car_image = cv2.resize(self.car_image, (xr - xl, yb - yt))

    def merge(self, imA, imB, k):
        G = self.weights[k]
        return (imA * G + imB * (1 - G)).astype(np.uint8)

    @property
    def FL(self):
        return self.image[:yt, :xl]

    @property
    def F(self):
        return self.image[:yt, xl:xr]

    @property
    def FR(self):
        return self.image[:yt, xr:]

    @property
    def BL(self):
        return self.image[yb:, :xl]

    @property
    def B(self):
        return self.image[yb:, xl:xr]

    @property
    def BR(self):
        return self.image[yb:, xr:]

    @property
    def L(self):
        return self.image[yt:yb, :xl]

    @property
    def R(self):
        return self.image[yt:yb, xr:]

    @property
    def C(self):
        return self.image[yt:yb, xl:xr]

    def stitch_all_parts(self, images):
        front, back, left, right = images
        np.copyto(self.F, FM(front))
        np.copyto(self.B, BM(back))
        np.copyto(self.L, LM(left))
        np.copyto(self.R, RM(right))
        np.copyto(self.FL, self.merge(FI(front), LI(left), 0))
        np.copyto(self.FR, self.merge(FII(front), RII(right), 1))
        np.copyto(self.BL, self.merge(BIII(back), LIII(left), 2))
        np.copyto(self.BR, self.merge(BIV(back), RIV(right), 3))

    def load_weights(self, weights_image_path, masks_image_path):
        from PIL import Image

        GMat = np.asarray(Image.open(weights_image_path).convert("RGBA"), dtype=np.float) / 255.0
        self.weights = [np.stack((GMat[:, :, k],
                                  GMat[:, :, k],
                                  GMat[:, :, k]), axis=2)
                        for k in range(4)]

        Mmat = np.asarray(Image.open(masks_image_path).convert("RGBA"), dtype=np.float) / 255.0
        self.masks = [Mmat.astype(np.int)[:, :, k] for k in range(4)]

    def run(self):
        if self.receive_buffer_manager is None:
            raise ValueError("This thread requires a buffer of projected images to run")

        while True:
            self.stop_mutex.lock()
            if self.stopped:
                self.stopped = False
                self.stop_mutex.unlock()
                break
            self.stop_mutex.unlock()
            self.processing_time = self.clock.elapsed()
            self.clock.start()

            self.processing_mutex.lock()

            frames = self.receive_buffer_manager.get()
            frame_images = frames.values()
            frame_images = self.make_luminance_balance(frame_images)
            self.stitch_all_parts(frame_images)
            self.make_white_balance()
            self.copy_car_image()
            self.buffer.add(self.image.copy(), self.drop_if_full)
            self.processing_mutex.unlock()

            # update statistics
            self.update_fps(self.processing_time)
            self.stat_data.frames_processed_count += 1
            # inform GUI of updated statistics
            self.update_statistics_gui.emit(self.stat_data)

    def copy_car_image(self):
        np.copyto(self.C, self.car_image)

    def get_weights(self, images):
        front, back, left, right = images
        G0, M0 = get_weight_matrix(FI(front), LI(left))
        G1, M1 = get_weight_matrix(FII(front), RII(right))
        G2, M2 = get_weight_matrix(BIII(back), LIII(left))
        G3, M3 = get_weight_matrix(BIV(back), RIV(right))
        self.weights = [np.stack((G, G, G), axis=2) for G in (G0, G1, G2, G3)]
        self.masks = [(M / 255.0).astype(np.int) for M in (M0, M1, M2, M3)]
        return np.stack((G0, G1, G2, G3), axis=2), np.stack((M0, M1, M2, M3), axis=2)

    def make_white_balance(self):
        self.image = make_white_balance(self.image)

    def make_luminance_balance(self, images):
        front, back, left, right = images
        M0, M1, M2, M3 = self.masks
        a1, a2, a3 = rgb_ratio(RII(right), FII(front), M1)
        b1, b2, b3 = rgb_ratio(BIV(back), RIV(right), M3)
        c1, c2, c3 = rgb_ratio(LIII(left), BIII(back), M2)
        d1, d2, d3 = rgb_ratio(FI(front), LI(left), M0)

        t1 = (a1*b1*c1*d1)**0.25
        t2 = (a2*b2*c2*d2)**0.25
        t3 = (a3*b3*c3*d3)**0.25
    
        e1 = t1 / (d1/a1)**0.5
        e2 = t2 / (d2/a2)**0.5
        e3 = t3 / (d3/a3)**0.5
        front = adjust_luminance_rgb(front, (e1, e2, e3))

        f1 = t1 / (b1/c1)**0.5
        f2 = t2 / (b2/c2)**0.5
        f3 = t3 / (b3/c3)**0.5
        back = adjust_luminance_rgb(back, (f1, f2, f3))
    
        g1 = t1 / (c1/d1)**0.5
        g2 = t2 / (c2/d2)**0.5
        g3 = t3 / (c3/d3)**0.5
        left = adjust_luminance_rgb(left, (g1, g2, g3))

        h1 = t1 / (a1/b1)**0.5
        h2 = t2 / (a2/b2)**0.5
        h3 = t3 / (a3/b3)**0.5
        right = adjust_luminance_rgb(right, (h1, h2, h3))
        
        return [front, back, left, right]
