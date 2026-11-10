"""Preview and identify local cameras.

Examples:
    python show_camera.py --camera-ids 2 3 5 4 0
    python show_camera.py --scan 0 12 --backend msmf

Keys in the preview window:
    q or Esc  quit
    s          save the current frames to --save-dir
"""

import argparse
import os
import time
from pathlib import Path

import cv2
import numpy as np


DEFAULT_CAMERA_IDS = [2, 3, 5, 4, 0]
BACKENDS = {
    "any": cv2.CAP_ANY,
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Preview and identify OpenCV camera devices")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--camera-ids",
        nargs="+",
        type=int,
        default=DEFAULT_CAMERA_IDS,
        help="Device IDs to open in the given order (default: 2 3 5 4 0)",
    )
    group.add_argument(
        "--scan",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="Scan IDs in the inclusive range START..END",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "any", "dshow", "msmf"],
        default="auto",
        help="Capture backend; auto tries the Windows backends in sequence",
    )
    parser.add_argument("--width", type=int, default=640, help="Requested capture width")
    parser.add_argument("--height", type=int, default=480, help="Requested capture height")
    parser.add_argument("--columns", type=int, default=3, help="Number of tiles per grid row")
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Open attempts per camera and backend (default: 3)",
    )
    parser.add_argument(
        "--save-dir",
        default="camera_snapshots",
        help="Directory used when pressing s (default: camera_snapshots)",
    )
    args = parser.parse_args()

    if args.scan is not None:
        start, end = args.scan
        if start < 0 or end < start:
            parser.error("--scan requires 0 <= START <= END")
        args.camera_ids = list(range(start, end + 1))
    if not args.camera_ids:
        parser.error("at least one camera ID is required")
    if len(set(args.camera_ids)) != len(args.camera_ids):
        parser.error("camera IDs must be unique")
    if args.width <= 0 or args.height <= 0:
        parser.error("--width and --height must be positive")
    if args.columns <= 0:
        parser.error("--columns must be positive")
    if args.retries <= 0:
        parser.error("--retries must be positive")
    return args


def backend_candidates(name):
    if name != "auto":
        return [(name, BACKENDS[name])]
    if os.name == "nt":
        return [("dshow", cv2.CAP_DSHOW), ("msmf", cv2.CAP_MSMF), ("any", cv2.CAP_ANY)]
    return [("any", cv2.CAP_ANY)]


def open_camera(camera_id, selected_name, api, width, height, retries):
    for attempt in range(retries):
        cap = cv2.VideoCapture(camera_id, api)
        if not cap.isOpened():
            cap.release()
            time.sleep(0.15)
            continue

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap, selected_name, frame
        cap.release()
        time.sleep(0.15)
    return None, None, None


def open_with_backend(camera_ids, backend_name, api, width, height, retries):
    captures = {}
    frames = {}
    for camera_id in camera_ids:
        cap, selected_name, first_frame = open_camera(
            camera_id, backend_name, api, width, height, retries
        )
        if cap is None:
            print(f"camera {camera_id}: unavailable with {backend_name}")
            continue
        captures[camera_id] = cap
        frames[camera_id] = first_frame
    return captures, frames


def choose_cameras(camera_ids, backend_name, width, height, retries):
    candidates = backend_candidates(backend_name)
    best = None
    for selected_name, api in candidates:
        captures, frames = open_with_backend(
            camera_ids, selected_name, api, width, height, retries
        )
        if best is None or len(captures) > len(best[1]):
            if best is not None:
                for cap in best[1].values():
                    cap.release()
            best = (selected_name, captures, frames)
        else:
            for cap in captures.values():
                cap.release()
        if len(captures) == len(camera_ids):
            break

    if best is None:
        return None, {}, {}
    selected_name, captures, frames = best
    print(f"selected backend: {selected_name}; opened {len(captures)}/{len(camera_ids)} camera(s)")
    if len(captures) < len(camera_ids):
        print("some devices could not be opened; close other camera applications and retry")
    return selected_name, captures, frames


def placeholder(camera_id, message, size):
    width, height = size
    image = np.full((height, width, 3), 42, dtype=np.uint8)
    cv2.putText(image, f"Camera ID {camera_id}", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 220, 255), 2)
    cv2.putText(image, message, (20, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 80, 255), 2)
    return image


def add_label(frame, camera_id, backend_name, ok=True):
    label = f"ID {camera_id} | {backend_name}" if ok else f"ID {camera_id} | read failed"
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 38), (20, 20, 20), -1)
    cv2.putText(frame, label, (12, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if ok else (0, 0, 255), 2)
    return frame


def make_grid(frames, columns, tile_size):
    tile_width, tile_height = tile_size
    rows = (len(frames) + columns - 1) // columns
    canvas = np.zeros((rows * tile_height, columns * tile_width, 3), dtype=np.uint8)
    for index, frame in enumerate(frames):
        row, column = divmod(index, columns)
        tile = cv2.resize(frame, tile_size, interpolation=cv2.INTER_AREA)
        y0, x0 = row * tile_height, column * tile_width
        canvas[y0:y0 + tile_height, x0:x0 + tile_width] = tile
    return canvas


def save_frames(frames, camera_ids, save_dir):
    output_dir = Path(save_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    saved = []
    for frame, camera_id in zip(frames, camera_ids):
        path = output_dir / f"camera_{camera_id}_{stamp}.jpg"
        if cv2.imwrite(str(path), frame):
            saved.append(str(path))
    print("saved {} frame(s): {}".format(len(saved), ", ".join(saved)))


def main():
    args = parse_args()
    captures = {}
    frames = {}
    backends = {}
    try:
        backend_name, captures, frames = choose_cameras(
            args.camera_ids,
            args.backend,
            args.width,
            args.height,
            args.retries,
        )
        for camera_id in args.camera_ids:
            if camera_id not in captures:
                frames[camera_id] = placeholder(camera_id, "unavailable", (args.width, args.height))
                continue
            backends[camera_id] = backend_name
            cap = captures[camera_id]
            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"camera {camera_id}: opened with {backend_name} at {actual_width}x{actual_height}")

        if not captures:
            raise SystemExit("No usable cameras found")

        window_name = "Camera Monitor"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        while True:
            display_frames = []
            for camera_id in args.camera_ids:
                cap = captures.get(camera_id)
                if cap is not None:
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        frames[camera_id] = frame
                        display_frames.append(add_label(frame.copy(), camera_id, backends[camera_id]))
                    else:
                        display_frames.append(add_label(
                            placeholder(camera_id, "read failed", (args.width, args.height)),
                            camera_id,
                            backends[camera_id],
                            ok=False,
                        ))
                else:
                    display_frames.append(frames[camera_id])

            grid = make_grid(display_frames, args.columns, (args.width, args.height))
            cv2.imshow(window_name, grid)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                save_frames(
                    [frames[camera_id] for camera_id in args.camera_ids],
                    args.camera_ids,
                    args.save_dir,
                )
    except KeyboardInterrupt:
        print("\nstopped by user")
    finally:
        for cap in captures.values():
            try:
                cap.release()
            except KeyboardInterrupt:
                break
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
