import cv2
import numpy as np


def gstreamer_pipeline(cam_id=0,
                       capture_width=960,
                       capture_height=640,
                       framerate=60,
                       flip_method=2):
    """
    Use libgstreamer to open csi-cameras.
    """
    return ("nvarguscamerasrc sensor-id={} ! ".format(cam_id) + \
            "video/x-raw(memory:NVMM), "
            "width=(int)%d, height=(int)%d, "
            "format=(string)NV12, framerate=(fraction)%d/1 ! "
            "nvvidconv flip-method=%d ! "
            "video/x-raw, format=(string)BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=(string)BGR ! appsink"
            % (capture_width,
               capture_height,
               framerate,
               flip_method
            )
    )


def convert_binary_to_bool(mask):
    """
    Convert a binary image (only one channel and pixels are 0 or 255) to
    a bool one (all pixels are 0 or 1).
    """
    return (mask.astype(np.float) / 255.0).astype(int)


def adjust_luminance(gray, factor):
    """
    Adjust the luminance of a grayscale image by a factor.
    """
    return np.minimum((gray * factor), 255).astype(np.uint8)


def get_mean_statistisc(gray, mask):
    """
    Get the total values of a gray image in a region defined by a mask matrix.
    The mask matrix must have values either 0 or 1.
    """
    return np.sum(gray * mask)


def mean_luminance_ratio(grayA, grayB, mask):
    return get_mean_statistisc(grayA, mask) / get_mean_statistisc(grayB, mask)


def get_mask(img):
    """
    Convert an image to a mask array.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY)
    return mask


def get_overlap_region_mask(imA, imB):
    """
    Given two images of the save size, get their overlapping region and
    convert this region to a mask array.
    """
    overlap = cv2.bitwise_and(imA, imB)
    mask = get_mask(overlap)
    mask = cv2.dilate(mask, np.ones((2, 2), np.uint8), iterations=2)
    return mask


def get_outmost_polygon_boundary(img):
    """
    Given a mask image with the mask describes the overlapping region of
    two images, get the outmost contour of this region.
    """
    mask = get_mask(img)
    mask = cv2.dilate(mask, np.ones((2, 2), np.uint8), iterations=2)
    cnts, hierarchy = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE)[-2:]

    # get the contour with largest aera
    C = sorted(cnts, key=lambda x: cv2.contourArea(x), reverse=True)[0]

    # polygon approximation
    polygon = cv2.approxPolyDP(C, 0.009 * cv2.arcLength(C, True), True)

    return polygon


def get_weight_mask_matrix(imA, imB, dist_threshold=5):
    """
    Get the weight matrix G that combines two images imA, imB smoothly.
    """
    overlapMask = get_overlap_region_mask(imA, imB)
    overlapMaskInv = cv2.bitwise_not(overlapMask)
    indices = np.where(overlapMask == 255)

    imA_diff = cv2.bitwise_and(imA, imA, mask=overlapMaskInv)
    imB_diff = cv2.bitwise_and(imB, imB, mask=overlapMaskInv)

    G = get_mask(imA).astype(np.float32) / 255.0

    polyA = get_outmost_polygon_boundary(imA_diff)
    polyB = get_outmost_polygon_boundary(imB_diff)

    for y, x in zip(*indices):

        #convert this x,y int an INT tuple
        xy_tuple = tuple([int(x), int(y)])
        distToB = cv2.pointPolygonTest(polyB, xy_tuple, True)

        if distToB < dist_threshold:
            distToA = cv2.pointPolygonTest(polyA, xy_tuple, True)
            distToB *= distToB
            distToA *= distToA
            G[y, x] = distToB / (distToA + distToB)

    return G, overlapMask


def make_white_balance(image):
    """
    Adjust white balance of an image base on the means of its channels.
    """
    B, G, R = cv2.split(image)
    m1 = np.mean(B)
    m2 = np.mean(G)
    m3 = np.mean(R)
    K = (m1 + m2 + m3) / 3
    c1 = K / m1
    c2 = K / m2
    c3 = K / m3
    B = adjust_luminance(B, c1)
    G = adjust_luminance(G, c2)
    R = adjust_luminance(R, c3)
    return cv2.merge((B, G, R))
