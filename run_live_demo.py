import argparse
import os
import cv2
from surround_view import CaptureThread, CameraProcessingThread
from surround_view import FisheyeCameraModel, BirdView
from surround_view import MultiBufferManager, ProjectedImageBuffer
import surround_view.param_settings as settings


DEFAULT_CAMERA_IDS = [2, 3, 5, 4, 0]
yamls_dir = os.path.join(os.getcwd(), "yaml")
flip_methods = [0, 2, 0, 2]
names = settings.camera_names
cameras_files = [os.path.join(yamls_dir, name + ".yaml") for name in names]
camera_models = [FisheyeCameraModel(camera_file, name) for camera_file, name in zip(cameras_files, names)]


def parse_args():
    parser = argparse.ArgumentParser(description="Four-camera surround view with optional fifth raw preview")
    parser.add_argument(
        "--camera-ids",
        nargs="+",
        default=DEFAULT_CAMERA_IDS,
        help="IDs in front back left right [center] order; e.g. --camera-ids 2 3 5 4",
    )
    parser.add_argument(
        "--gst",
        action="store_true",
        help="Use the Jetson GStreamer camera pipeline instead of the local camera backend",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "any", "dshow", "msmf"],
        default="auto",
        help="Local camera backend; auto uses OpenCV's backend selection",
    )
    args = parser.parse_args()
    values = []
    try:
        for item in args.camera_ids:
            values.extend(int(value.strip()) for value in item.split(",") if value.strip())
    except ValueError:
        parser.error("--camera-ids must contain integers, separated by spaces or commas")
    if len(values) not in (4, 5):
        parser.error("--camera-ids must contain four outer camera IDs and optionally one center ID")
    if len(set(values)) != len(values):
        parser.error("--camera-ids must not repeat device IDs")
    args.outer_camera_ids = values[:4]
    args.center_camera_id = values[4] if len(values) == 5 else None
    return args


def main():
    args = parse_args()
    use_gst = args.gst
    if use_gst:
        camera_backend = cv2.CAP_GSTREAMER
    elif args.backend == "dshow":
        camera_backend = cv2.CAP_DSHOW
    elif args.backend == "msmf":
        camera_backend = cv2.CAP_MSMF
    else:
        camera_backend = cv2.CAP_ANY
    capture_tds = []
    started_capture_tds = []
    process_tds = []
    capture_buffer_manager = None
    proc_buffer_manager = None
    birdview = None
    center_cap = None

    try:
        camera_models_by_id = dict(zip(args.outer_camera_ids, camera_models))
        capture_tds = [
            CaptureThread(
                camera_id,
                flip_method,
                use_gst=use_gst,
                api_preference=camera_backend,
            )
            for camera_id, flip_method in zip(args.outer_camera_ids, flip_methods)
        ]
        capture_buffer_manager = MultiBufferManager()
        connected_cameras = []
        for td in capture_tds:
            if td.connect_camera():
                capture_buffer_manager.bind_thread(td, buffer_size=8)
                td.start()
                started_capture_tds.append(td)
                connected_cameras.append(td.device_id)
                print("opened {} camera on device {} at {}x{}".format(
                    camera_models_by_id[td.device_id].camera_name,
                    td.device_id,
                    td.resolution[0],
                    td.resolution[1],
                ))
            else:
                print("failed to open camera on device {}".format(td.device_id))

        if not connected_cameras:
            print("No cameras could be connected. Please check your camera devices.")
            return

        missing_cameras = [camera_id for camera_id in args.outer_camera_ids if camera_id not in connected_cameras]
        if missing_cameras:
            print("Missing required outer cameras: {}".format(",".join(map(str, missing_cameras))))
            print("Close other camera applications and retry; the stitch requires all four outer cameras.")
            return

        proc_buffer_manager = ProjectedImageBuffer()
        process_tds = []
        for td in capture_tds:
            if td.device_id in connected_cameras:
                pt = CameraProcessingThread(capture_buffer_manager,
                                             td.device_id,
                                             camera_models_by_id[td.device_id])
                process_tds.append(pt)
                proc_buffer_manager.bind_thread(pt)
                pt.start()

        birdview = BirdView(proc_buffer_manager)
        birdview.load_weights_and_masks("./weights.png", "./masks.png")
        birdview.start()

        if args.center_camera_id is not None:
            center_cap = cv2.VideoCapture(args.center_camera_id, camera_backend)
            if not center_cap.isOpened():
                print("failed to open center preview camera on device {}".format(args.center_camera_id))
                center_cap.release()
                center_cap = None
            else:
                print("opened center raw preview on device {} (not included in the calibrated stitch)".format(
                    args.center_camera_id
                ))

        while True:
            frame = birdview.get(timeout_ms=1000)
            if frame is None:
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                continue
            img = cv2.resize(frame, (300, 400))
            cv2.imshow("birdview", img)
            if center_cap is not None:
                center_ok, center_frame = center_cap.read()
                if center_ok and center_frame is not None:
                    cv2.imshow("center raw preview", center_frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

            for td in capture_tds:
                print("camera {} fps: {}\n".format(td.device_id, td.stat_data.average_fps), end="\r")

            for td in process_tds:
                print("process {} fps: {}\n".format(td.device_id, td.stat_data.average_fps), end="\r")

            print("birdview fps: {}".format(birdview.stat_data.average_fps))

    except KeyboardInterrupt:
        print("\nInterrupted by user, shutting down...")

    finally:
        # Stop every worker before waking barriers so shutdown cannot wait on
        # another thread that is still producing frames.
        if birdview is not None and birdview.isRunning():
            birdview.stop()
        for td in process_tds:
            td.stop()
        for td in started_capture_tds:
            td.stop()

        if proc_buffer_manager is not None:
            proc_buffer_manager.wake_all()
        if capture_buffer_manager is not None:
            capture_buffer_manager.wake_all()

        if center_cap is not None:
            center_cap.release()
        for td in started_capture_tds:
            td.disconnect_camera()

        threads_to_stop = process_tds + started_capture_tds
        if birdview is not None:
            threads_to_stop.append(birdview)
        for thread in threads_to_stop:
            if thread.isRunning() and not thread.wait(3000):
                if proc_buffer_manager is not None:
                    proc_buffer_manager.wake_all()
                if capture_buffer_manager is not None:
                    capture_buffer_manager.wake_all()
                thread.wait(1000)
            if thread.isRunning():
                print("warning: {} did not stop within 4 seconds".format(thread.__class__.__name__))

        if proc_buffer_manager is not None:
            for td in process_tds:
                proc_buffer_manager.remove_device(td.device_id)
        for td in started_capture_tds:
            if capture_buffer_manager is not None:
                capture_buffer_manager.remove_device(td.device_id)

        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
