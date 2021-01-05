import cv2
import numpy as np

# return -1 if user press 'q'. return 1 if user press 'Enter'.
def display_image(window_title, image):
    cv2.imshow(window_title, image)
    while True:
        click = cv2.getWindowProperty(window_title, cv2.WND_PROP_AUTOSIZE)
        if click < 0:
            return -1

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            return -1

        # 'Enter' key is detected!
        if key == 13:
            return 1


class PointSelector(object):

    """
    ---------------------------------------------------
    | A simple gui point selector.                    |
    | Usage:                                          |
    |                                                 |
    | 1. call the `loop` method to show the image.    |
    | 2. click on the image to select key points,     |
    |    press `d` to delete the last points.         |
    | 3. press `q` to quit, press `Enter` to confirm. |
    ---------------------------------------------------
    """

    POINT_COLOR = (0, 0, 255)
    FILL_COLOR = (0, 255, 255)

    def __init__(self, image, title="PointSelector"):
        self.image = image
        self.title = title
        self.keypoints = []

    def draw_image(self):
        """
        Display the selected keypoints and draw the convex hull.
        """
        # the trick: draw on another new image
        new_image = self.image.copy()

        # draw the selected keypoints
        for i, pt in enumerate(self.keypoints):
            cv2.circle(new_image, pt, 6, self.POINT_COLOR, -1)
            cv2.putText(new_image, str(i), (pt[0], pt[1] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.POINT_COLOR, 2)

        # draw a line if there are two points
        if len(self.keypoints) == 2:
            p1, p2 = self.keypoints
            cv2.line(new_image, p1, p2, self.POINT_COLOR, 2)

        # draw the convex hull if there are more than two points
        if len(self.keypoints) > 2:
            mask = self.create_mask_from_pixels(self.keypoints,
                                                self.image.shape)
            new_image = self.draw_mask_on_image(new_image, mask)

        cv2.imshow(self.title, new_image)

    def onclick(self, event, x, y, flags, param):
        """
        Click on a point (x, y) will add this points to the list
        and re-draw the image.
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            print("click ({}, {})".format(x, y))
            self.keypoints.append((x, y))
            self.draw_image()

    def loop(self):
        """
        Press "q" will exist the gui and return False
        press "d" will delete the last selected point.
        Press "Enter" will exist the gui and return True.
        """
        cv2.namedWindow(self.title)
        cv2.setMouseCallback(self.title, self.onclick, param=())
        cv2.imshow(self.title, self.image)

        while True:
            click = cv2.getWindowProperty(self.title, cv2.WND_PROP_AUTOSIZE)
            if click < 0:
                return False

            key = cv2.waitKey(1) & 0xFF

            # press q to return False
            if key == ord("q"):
                return False

            # press d to delete the last point
            if key == ord("d"):
                if len(self.keypoints) > 0:
                    x, y = self.keypoints.pop()
                    print("Delete ({}, {})".format(x, y))
                    self.draw_image()

            # press Enter to confirm
            if key == 13:
                return True

    def create_mask_from_pixels(self, pixels, image_shape):
        """
        Create mask from the convex hull of a list of pixels.
        """
        pixels = np.int32(pixels).reshape(-1, 2)
        hull = cv2.convexHull(pixels)
        mask = np.zeros(image_shape[:2], np.int8)
        cv2.fillConvexPoly(mask, hull, 1, lineType=8, shift=0)
        mask = mask.astype(np.bool)
        return mask

    def draw_mask_on_image(self, image, mask):
        """
        Paint the region defined by a given mask on an image.
        """
        new_image = np.zeros_like(image)
        new_image[:, :] = self.FILL_COLOR
        mask = np.array(mask, dtype=np.uint8)
        new_mask = cv2.bitwise_and(new_image, new_image, mask=mask)
        cv2.addWeighted(image, 1.0, new_mask, 0.5, 0.0, image)
        return image
