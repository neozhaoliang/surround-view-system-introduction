# (shift_width, shift_height): how far away the birdview looks outside
# of the calibration pattern in horizontal and vertical directions
shift_w = 300
shift_h = 300

# size of the gap between the calibration pattern and the car
# in horizontal and vertical directions
inn_shift_w = 20
inn_shift_h = 50

# total width/height of the stitched image
total_w = 600 + 2 * shift_w
total_h = 1000 + 2 * shift_h

# four corners of the rectangular region occupied by the car
# top-left (x_left, y_top), bottom-right (x_right, y_bottom)
xl = shift_w + 180 + inn_shift_w
xr = total_w - xl
yt = shift_h + 200 + inn_shift_h
yb = total_h - yt

# ------------------------------------------------------------
camera_names = ("front", "back", "left", "right")

front_shape = (total_w, yt)
back_shape = front_shape
left_shape = (total_h, xl)
right_shape = left_shape

project_shapes = {
    "front": front_shape,
    "back": back_shape,
    "left": left_shape,
    "right": right_shape
}

# pixel locations of the four points to be choosen.
# you must click these pixels in the same order when running
# the get_projection_map.py script.
front_proj_keypoints = [(shift_w + 120, shift_h),
                        (shift_w + 480, shift_h),
                        (shift_w + 120, shift_h + 160),
                        (shift_w + 480, shift_h + 160)]

back_proj_keypoints = [(shift_w + 120, shift_h),
                       (shift_w + 480, shift_h),
                       (shift_w + 120, shift_h + 160),
                       (shift_w + 480, shift_h + 160)]

left_proj_keypoints = [(shift_h + 280, shift_w),
                       (shift_h + 840, shift_w),
                       (shift_h + 280, shift_w + 160),
                       (shift_h + 840, shift_w + 160)]

right_proj_keypoints = [(shift_h + 160, shift_w),
                        (shift_h + 720, shift_w),
                        (shift_h + 160, shift_w + 160),
                        (shift_h + 720, shift_w + 160)]

dst_points = {
    "front": front_proj_keypoints,
    "back": back_proj_keypoints,
    "left": left_proj_keypoints,
    "right": right_proj_keypoints
}
