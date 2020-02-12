"""
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Manually select points to get the projection map
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""
import cv2
import numpy as np
import yaml
import os
from paramsettings import *


name = "front"
image_file = "./yaml/{}.png".format(name)
camera_file = "./yaml/{}.yaml".format(name)
output = "./yaml/{}_projmat.yaml".format(name)

W, H = 640, 480
colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255)]
corners = []

shapes = {
    "front": frontShape[::-1],
    "back": frontShape[::-1],
    "left": leftShape[::-1],
    "right": leftShape[::-1]
}

dstF = np.float32([
    [shiftWidth, shiftHeight],
    [totalWidth-shiftWidth, shiftHeight],
    [shiftWidth, shiftHeight+chessboardSize],
    [totalWidth-shiftWidth,  shiftHeight+chessboardSize]])

dstL = np.float32([
    [shiftHeight, shiftWidth],
    [totalHeight-shiftHeight, shiftWidth],
    [shiftHeight, shiftWidth+chessboardSize],
    [totalHeight-shiftHeight, shiftWidth+chessboardSize]])

dsts = {"front": dstF, "back": dstF, "left": dstL, "right": dstL}


def click(event, x, y, flags, param):
    image, = param
    if event == cv2.EVENT_LBUTTONDOWN:
        print(x, y)
        corners.append((x, y))
    draw_image(image)


def draw_image(image):

    new_image = image.copy()
    for i, point in enumerate(corners):
        cv2.circle(new_image, point, 6, colors[i % 4], -1)

    if len(corners) > 2:
        pts = np.int32(corners).reshape(-1, 2)
        hull = cv2.convexHull(pts)
        mask = np.zeros(image.shape[:2], np.uint8)
        cv2.fillConvexPoly(mask, hull, color=1, lineType=8, shift=0)
        temp = np.zeros_like(image, np.uint8)
        temp[:, :] = [0, 0, 255]
        imB = cv2.bitwise_and(temp, temp, mask=mask)
        cv2.addWeighted(new_image, 0.5, imB, 0.5, 1.0, new_image)

    cv2.imshow("original image", new_image)


def main():
    image = cv2.imread(image_file)
    with open(camera_file, "r") as f:
        data = yaml.load(f)

    K = np.array(data["K"])
    D = np.array(data["D"])
    new_K = K.copy()
    new_K[0, 0] *= 0.6
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(
        K,
        D,
        np.eye(3),
        new_K,
        (W, H),
        cv2.CV_16SC2
    )
    image = cv2.remap(
        image,
        map1,
        map2,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT
    )
    cv2.namedWindow("original image")
    cv2.setMouseCallback("original image", click, param=[image])
    cv2.imshow("original image", image)
    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            return
        elif key == ord("d"):
            if len(corners) > 0:
                corners.pop()
                draw_image(image)
        elif key == 13:
            break

    if len(corners) != 4:
        print("exactly 4 corners are required")
        return

    src = np.float32(corners)
    dst = dsts[name]
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image, M, shapes[name][1::-1])
    cv2.imshow("warped", warped)
    cv2.waitKey(0)
    cv2.imwrite(name + "_proj.png", warped)
    print("saving projection matrix to file ...")
    with open(output, "w") as f:
        yaml.dump({"M": M.tolist()}, f)


if __name__ == "__main__":
    main()
