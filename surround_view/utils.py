import numpy as np
import cv2


def convert_mask(image):
    """
    Convert an image to a mask array.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ret, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY)
    return mask


def get_overlap_region_mask(imA, imB):
    """
    Given two images of the save size, get their overlapping region and
    convert this region to a mask array.
    """
    overlap = cv2.bitwise_and(imA, imB)
    mask = convert_mask(overlap)
    mask = cv2.dilate(mask, np.ones((2, 2), np.uint8), iterations=2)
    return mask


def get_outmost_polygon_boundary(image):
    """
    Given a mask image with the mask describes the overlapping region of
    two images, get the outmost contour of this region.
    """
    mask = convert_mask(image)
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


def get_weight_matrix(imA, imB):
    """
    Get the weight matrix G that combines two images imA, imB smoothly.
    """
    overlapMask = get_overlap_region_mask(imA, imB)
    overlapMaskInv = cv2.bitwise_not(overlapMask)
    indices = np.where(overlapMask == 255)

    imA_diff = cv2.bitwise_and(imA, imA, mask=overlapMaskInv)
    imB_diff = cv2.bitwise_and(imB, imB, mask=overlapMaskInv)

    G = convert_mask(imA).astype(np.float32) / 255.0

    polyA = get_outmost_polygon_boundary(imA_diff)
    polyB = get_outmost_polygon_boundary(imB_diff)

    for y, x in zip(*indices):
        distToB = cv2.pointPolygonTest(polyB, (x, y), True)
        if distToB < 1:
            distToA = cv2.pointPolygonTest(polyA, (x, y), True)
            distToB *= distToB
            distToA *= distToA
            G[y, x] = distToB / (distToA + distToB)

    return G, overlapMask


def adjust_luminance(gray, factor):
    """
    Adjust the luminance of a grayscale image by a factor.
    """
    return np.minimum((gray * factor), 255).astype(np.uint8)


def adjust_luminance_rgb(image, rgb_triple):
    R, G, B = cv2.split(image)
    a, b, c = rgb_triple
    R = adjust_luminance(R, a)
    G = adjust_luminance(G, b)
    B = adjust_luminance(B, c)
    return cv2.merge((R, G, B))


def get_mean_statistisc(gray, mask):
    """
    Get the total values of a gray image in a region defined by a mask matrix.
    The mask matrix must have values either 0 or 1.
    """
    return np.sum(gray * mask)


def rgb_ratio(imA, imB, mask=None):
    """
    Compute the ratios of the (R, G, B) channels of two images base on
    their overlapping region.
    """
    if mask is None:
        mask = get_overlap_region_mask(imA, imB)
        mask = (mask.astype(np.float) / 255).astype(np.int)

    B1, G1, R1 = cv2.split(imA)
    B2, G2, R2 = cv2.split(imB)
    c1 = get_mean_statistisc(B1, mask) / get_mean_statistisc(B2, mask)
    c2 = get_mean_statistisc(G1, mask) / get_mean_statistisc(G2, mask)
    c3 = get_mean_statistisc(R1, mask) / get_mean_statistisc(R2, mask)
    return c1, c2, c3


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
