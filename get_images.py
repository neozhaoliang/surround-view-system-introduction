"""
~~~~~~~~~~~~~~~~~~~~~~~~~~
Get image from camera saved in images folder
~~~~~~~~~~~~~~~~~~~~~~~~~~
Usage:
    python get_images.py \
        -i 0 \
        -r 640x480 \
"--no_gst" add this flag if using USB cameras
"""

import os
import cv2
import argparse
from surround_view import CaptureThread, MultiBufferManager
import surround_view.param_settings as settings


def save_image(img, device_id):
    camera_name = settings.camera_names[device_id]
    filename = f"{camera_name}.png"
    save_path = os.path.join(os.getcwd(), "images", filename)
    cv2.imwrite(save_path, img)
    print(f"Image saved to {save_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i", "--input", type=int, default=0, help="Input camera device"
    )
    parser.add_argument(
        "-r", "--resolution", default="640x480", help="resolution of the camera image"
    )
    parser.add_argument(
        "-o", "--output", default="front", help="path to output yaml file"
    )
    parser.add_argument(
        "-flip", "--flip", default=0, type=int, help="flip method of the camera"
    )
    parser.add_argument(
        "--no_gst",
        action="store_true",
        help="set true if not use gstreamer for the camera capture",
    )
    args = parser.parse_args()
    images_dir = os.path.join(os.getcwd(), "images")
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)

    text1 = "press s to save"
    text2 = "press q to quit"
    text3 = "device: {}".format(args.input)
    font = cv2.FONT_HERSHEY_SIMPLEX
    fontscale = 0.6

    resolution_str = args.resolution.split("x")
    W = int(resolution_str[0])
    H = int(resolution_str[1])
    device = args.input
    cap_thread = CaptureThread(
        device_id=device,
        flip_method=args.flip,
        resolution=(W, H),
        use_gst=not args.no_gst,
    )
    buffer_manager = MultiBufferManager()
    buffer_manager.bind_thread(cap_thread, buffer_size=8)

    if cap_thread.connect_camera():
        cap_thread.start()
    else:
        print("cannot open device")
        return

    while True:
        img = buffer_manager.get_device(device).get().image
        cv2.putText(img, text1, (20, 70), font, fontscale, (255, 200, 0), 2)
        cv2.putText(img, text2, (20, 110), font, fontscale, (255, 200, 0), 2)
        cv2.putText(img, text3, (20, 30), font, fontscale, (255, 200, 0), 2)
        cv2.imshow("Frame", img)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("s"):
            save_image(img, device)
            break

    cap_thread.stop()
    cap_thread.disconnect_camera()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
