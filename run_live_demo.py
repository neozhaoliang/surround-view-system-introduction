import os
import cv2
from surround_view import CaptureThread, CameraProcessingThread
from surround_view import FisheyeCameraModel, BirdView
from surround_view import MultiBufferManager, ProjectedImageBuffer
import surround_view.param_settings as settings


yamls_dir = os.path.join(os.getcwd(), "yaml")
camera_ids = [4, 3, 5, 6]
flip_methods = [0, 2, 0, 2]
names = settings.camera_names
cameras_files = [os.path.join(yamls_dir, name + ".yaml") for name in names]
camera_models = [FisheyeCameraModel(camera_file, name) for camera_file, name in zip(cameras_files, names)]


def main():
    capture_tds = []
    started_capture_tds = []
    process_tds = []
    capture_buffer_manager = None
    proc_buffer_manager = None
    birdview = None

    try:
        capture_tds = [CaptureThread(camera_id, flip_method)
                       for camera_id, flip_method in zip(camera_ids, flip_methods)]
        capture_buffer_manager = MultiBufferManager()
        connected_cameras = []
        for td in capture_tds:
            if td.connect_camera():
                capture_buffer_manager.bind_thread(td, buffer_size=8)
                td.start()
                started_capture_tds.append(td)
                connected_cameras.append(td.device_id)

        if not connected_cameras:
            print("No cameras could be connected. Please check your camera devices.")
            return

        proc_buffer_manager = ProjectedImageBuffer()
        process_tds = []
        for td in capture_tds:
            if td.device_id in connected_cameras:
                idx = camera_ids.index(td.device_id)
                pt = CameraProcessingThread(capture_buffer_manager,
                                             td.device_id,
                                             camera_models[idx])
                process_tds.append(pt)
                proc_buffer_manager.bind_thread(pt)
                pt.start()

        birdview = BirdView(proc_buffer_manager)
        birdview.load_weights_and_masks("./weights.png", "./masks.png")
        birdview.start()
        while True:
            frame = birdview.get(timeout_ms=1000)
            if frame is None:
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                continue
            img = cv2.resize(frame, (300, 400))
            cv2.imshow("birdview", img)
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
        if birdview is not None:
            birdview.stop()
            birdview.wait()

        for td in process_tds:
            td.stop()

        if proc_buffer_manager is not None:
            for td in process_tds:
                proc_buffer_manager.remove_device(td.device_id)
            proc_buffer_manager.wake_all()

        for td in process_tds:
            td.wait()

        for td in started_capture_tds:
            td.stop()

        if capture_buffer_manager is not None:
            for td in started_capture_tds:
                capture_buffer_manager.remove_device(td.device_id)
            capture_buffer_manager.wake_all()

        for td in started_capture_tds:
            td.wait()
            td.disconnect_camera()

        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
