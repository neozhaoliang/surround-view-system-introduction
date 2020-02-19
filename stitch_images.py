"""
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stitch four camera images to form the 360 surround view
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""
import numpy as np
import cv2
import yaml
import os
from paramsettings import *


W, H = 640, 480
work_dir = "./yaml"
car_image = os.path.join(work_dir, "car.png")
camera_params = [os.path.join(work_dir, f) for f in ("front.yaml", "back.yaml", "left.yaml", "right.yaml")]
camera_images = [os.path.join(work_dir, f) for f in ("front.png", "back.png", "left.png", "right.png")]


def dline(x, y, x1, y1, x2, y2):
    """Compute a pixel (x, y) to line segment (x1, y1) and (x2, y2).
    """
    vx, vy = x2 - x1, y2 - y1
    dx, dy = x - x1, y - y1
    a = np.sqrt(vx * vx + vy * vy)
    return abs(vx * dy - dx * vy) / a


def linelen(line):
    """Compute the length of a line segment.
    """
    x1, y1, x2, y2 = line[0]
    dx, dy = x1 - x2, y1 - y2
    return np.sqrt(dx*dx + dy*dy)


def get_weight_matrix(imA, imB):
    overlap = cv2.bitwise_and(imA, imB)
    gray = cv2.cvtColor(overlap, cv2.COLOR_BGR2GRAY)
    ret, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY)
    mask = cv2.dilate(mask, np.ones((2, 2), np.uint8), iterations=2)
    mask_inv = cv2.bitwise_not(mask)
    imA_remain = cv2.bitwise_and(imA, imA, mask=mask_inv)
    grayA = cv2.cvtColor(imA_remain, cv2.COLOR_BGR2GRAY)
    ret, G = cv2.threshold(grayA, 0, 255, cv2.THRESH_BINARY)
    G = G.astype(np.float32) / 255.0
    ind = np.where(mask == 255)
    lsd = cv2.createLineSegmentDetector(0)
    lines = lsd.detect(mask)[0]
    lines = sorted(lines, key=linelen, reverse=True)[1::-1]
    lx1, ly1, lx2, ly2 = lines[0][0]
    mx1, my1, mx2, my2 = lines[1][0]
    for y, x in zip(*ind):
        d1 = dline(x, y, lx1, ly1, lx2, ly2)
        d2 = dline(x, y, mx1, my1, mx2, my2)
        d1 *= d1
        d2 *= d2
        G[y, x] = d1 / (d1 + d2)

    return G


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


def main(save_weights=False):
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

    images = [cv2.imread(im) for im in camera_images]
    for i, image in enumerate(images):
        map1, map2 = undistort_maps[i]
        images[i] = cv2.remap(image, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    front = cv2.warpPerspective(
        images[0],
        matrices[0],
        frontShape
    )
    back = cv2.warpPerspective(
        images[1],
        matrices[1],
        frontShape
    )
    left = cv2.warpPerspective(
        images[2],
        matrices[2],
        leftShape
    )
    right = cv2.warpPerspective(
        images[3],
        matrices[3],
        leftShape
    )

    back = back[::-1, ::-1, :]
    left = cv2.transpose(left)[::-1]
    right = np.flip(cv2.transpose(right), 1)

    result = np.zeros((totalHeight, totalWidth, 3), dtype=np.uint8)

    car = cv2.imread(car_image)
    car = cv2.resize(car, (x2 - x1, y2 - y1))

    weights = [None] * 4
    weights[0] = get_weight_matrix(front[:, :x1], left[:y1])
    weights[1] = get_weight_matrix(back[:, :x1], left[y2:])
    weights[2] = get_weight_matrix(front[:, x2:], right[:y1])
    weights[3] = get_weight_matrix(back[:, x2:], right[y2:])

    stacked_weights = [np.stack((G, G, G), axis=2) for G in weights]

    def merge(imA, imB, k):
        G = stacked_weights[k]
        return G * imA + imB * (1 - G)

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

    result[y1:y2, x1:x2] = car
    cv2.imshow("result", result)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    if save_weights:
        mats = {
            "G0": weights[0].tolist(),
            "G1": weights[1].tolist(),
            "G2": weights[2].tolist(),
            "G3": weights[3].tolist(),
        }

        with open(os.path.join(work_dir, "weights.yaml"), "w") as f:
            yaml.safe_dump(mats, f)


if __name__ == "__main__":
    main(save_weights=True)
