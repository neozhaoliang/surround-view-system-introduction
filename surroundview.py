"""
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Show the projected 360 surround view of four cameras
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Press Esc to exit.
"""
import numpy as np
import cv2
import yaml
import os
import time
from imutils.video import VideoStream
from paramsettings import *


# -----------------
# Global parameters
# -----------------
W, H = 640, 480  # camera resolution
window_title = "Carview"
camera_devices = [0, 1, 2, 3]  # camera devices front, back, left, right
yaml_dir = "./yaml"
camera_params = [os.path.join(yaml_dir, f) for f in ("front.yaml", "back.yaml", "left.yaml", "right.yaml")]
weights_file = os.path.join(yaml_dir, "weights.yaml")
car_icon = os.path.join(yaml_dir, "car.png")


def adjust_illuminance(im, a):
    return np.minimum((im.astype(np.float) * a), 255).astype(np.uint8)


def rgb_ratio(imA, imB):
    overlap = cv2.bitwise_and(imA, imB)
    gray = cv2.cvtColor(overlap, cv2.COLOR_BGR2GRAY)
    ret, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY)
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=4)
    imA_here = cv2.bitwise_and(imA, imA, mask=mask)
    imB_here = cv2.bitwise_and(imB, imB, mask=mask)
    B1, G1, R1 = cv2.split(imA_here)
    B2, G2, R2 = cv2.split(imB_here)
    c1 = np.mean(B1) / np.mean(B2)
    c2 = np.mean(G1) / np.mean(G2)
    c3 = np.mean(R1) / np.mean(R2)
    return c1, c2, c3


def main():
    print("[INFO] openning camera devices...")
    captures = [VideoStream(src=k, resolution=(W, H)).start() for k in camera_devices]
    time.sleep(2)
    print("[INFO] loading camera intrinsic parameters...")
    matrices = []
    undistort_maps = []
    for conf in camera_params:
        with open(conf, "r") as f:
            data = yaml.load(f, Loader=yaml.SafeLoader)

        proj_mat = np.array(data["M"])
        matrices.append(proj_mat)

        K = np.array(data["K"])
        D = np.array(data["D"])
        scale = np.array(data["scale"])
        new_K = K.copy()
        new_K[0, 0] *= scale[0]
        new_K[1, 1] *= scale[1]
        map1, map2 = cv2.fisheye.initUndistortRectifyMap(
            K,
            D,
            np.eye(3),
            new_K,
            (W, H),
            cv2.CV_16SC2
        )
        undistort_maps.append((map1, map2))

    print("[INFO] loading weight matrices...")
    with open(weights_file, "r") as f:
        data = yaml.load(f)
        G0 = np.array(data["G0"])
        G1 = np.array(data["G1"])
        G2 = np.array(data["G2"])
        G3 = np.array(data["G3"])
        weights = [np.stack((G, G, G), axis=2) for G in (G0, G1, G2, G3)]

    def merge(imA, imB, k):
        G = weights[k]
        return G * imA + imB * (1 - G)

    car = cv2.imread(car_icon)
    car = cv2.resize(car, (x2 - x1, y2 - y1))

    cv2.namedWindow(window_title)
    cv2.moveWindow(window_title, 1500, 0)
    result = np.zeros((totalHeight, totalWidth, 3), np.uint8)

    while True:
        frames = []
        for i, cap in enumerate(captures):
            frame = cap.read()
            map1, map2 = undistort_maps[i]
            frame = cv2.remap(frame, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            frames.append(frame)

        front = cv2.warpPerspective(
            frames[0],
            matrices[0],
            frontShape
        )
        back = cv2.warpPerspective(
            frames[1],
            matrices[1],
            frontShape
        )
        left = cv2.warpPerspective(
            frames[2],
            matrices[2],
            leftShape
        )
        right = cv2.warpPerspective(
            frames[3],
            matrices[3],
            leftShape
        )

        # flip the images
        back = back[::-1, ::-1, :]
        left = cv2.transpose(left)[::-1]
        right = np.flip(cv2.transpose(right), 1)

        # top-left
        FL = merge(front[:, :x1], left[:y1], 0)
        result[:y1, :x1] = FL
        # bottom-left
        BL = merge(back[:, :x1], left[y2:], 1)
        result[y2:, :x1] = BL
        # top-right
        FR = merge(front[:, x2:], right[:y1], 2)
        result[:y1, x2:] = FR
        # bottom-right
        BR = merge(back[:, x2:], right[y2:], 3)
        result[y2:, x2:] = BR

        # front
        F = front[:, x1:x2]
        result[:y1, x1:x2] = F
        # back
        B = back[:, x1:x2]
        result[y2:, x1:x2] = B
        # left
        L = left[y1:y2]
        result[y1:y2, :x1] = L
        # right
        R = right[y1:y2]
        result[y1:y2, x2:] = R

        a1, a2, a3 = rgb_ratio(right[:y1], front[:, x2:])
        b1, b2, b3 = rgb_ratio(back[:, x2:], right[y2:])
        c1, c2, c3 = rgb_ratio(left[y2:], back[:, :x1])
        d1, d2, d3 = rgb_ratio(front[:, :x1], left[:y1])

        e1 = (a1 + b1 + c1 + d1) / (a1*a1 + b1*b1 + c1*c1 + d1*d1)
        e2 = (a2 + b2 + c2 + d2) / (a2*a2 + b2*b2 + c2*c2 + d2*d2)
        e3 = (a3 + b3 + c3 + d3) / (a3*a3 + b3*b3 + c3*c3 + d3*d3)

        ch1, ch2, ch3 = cv2.split(result)
        ch1 = adjust_illuminance(ch1, e1)
        ch2 = adjust_illuminance(ch2, e2)
        ch3 = adjust_illuminance(ch3, e3)

        result = cv2.merge((ch1, ch2, ch3))
        result[y1:y2, x1:x2] = car  # add car icon
        cv2.imshow(window_title, result)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break

    time.sleep(2)

    for cap in captures:
        cap.stop()

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
