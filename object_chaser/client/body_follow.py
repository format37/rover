"""Main loop: fetch frames, run YOLO, call chase logic."""
import time
import argparse
import asyncio
import json
import logging
import aiohttp
import cv2
import numpy as np
import chase

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logging.getLogger('chase').setLevel(logging.INFO)
logging.getLogger('chase').addHandler(handler)

YOLO_URL = 'http://localhost:8765'
CAMERA_URL = 'http://localhost:8080'
STALE_FRAME_SECONDS = 2.0

_prev_ts = None
_prev_ts_time = None


def is_frame_stale(ts):
    global _prev_ts, _prev_ts_time
    now = time.monotonic()
    if ts != _prev_ts:
        _prev_ts = ts
        _prev_ts_time = now
        return False
    if _prev_ts_time is not None:
        return (now - _prev_ts_time) > STALE_FRAME_SECONDS
    return False


async def run(label='person'):
    import requests
    print(f"Body follow: tracking '{label}' (Ctrl+C to stop)")

    # Session info
    try:
        r = requests.get(f"{CAMERA_URL}/session", timeout=2.0)
        info = r.json()
        yolo_dir = info['yolo_dir']
        logger.info(f"Session: {info['session_path']}")
    except Exception as e:
        logger.error(f"Cannot connect to camera server: {e}")
        return

    jsonl_file = open(f"{yolo_dir}/detections.jsonl", 'a')
    logger.info(f"Logging to {yolo_dir}/detections.jsonl")

    async with aiohttp.ClientSession() as session:
        try:
            while True:
                # Fetch frame
                async with session.get(f"{CAMERA_URL}/frame") as resp:
                    if resp.status != 200:
                        await asyncio.sleep(0.1)
                        continue
                    image_data = await resp.read()
                    frame_ts = resp.headers.get('X-Timestamp', '')

                if is_frame_stale(frame_ts):
                    await asyncio.sleep(0.1)
                    continue

                # YOLO
                async with session.post(
                        f"{YOLO_URL}/detect/",
                        data={'file': image_data}) as resp:
                    if resp.status != 200:
                        continue
                    result = await resp.json()

                detections = [d for d in result['detections']
                              if d['label'] == label]

                action = "no_detection"
                target_bbox = None
                target_conf = None
                x_normalized = None
                distance = None
                servo_angle = None

                if detections:
                    chase.reset_search()
                    best = max(detections, key=lambda d: d['confidence'])
                    target_bbox = best['bbox']
                    target_conf = best['confidence']

                    # Object position in frame
                    arr = np.frombuffer(image_data, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    x_mid = best['bbox'][0] + best['bbox'][2] / 2
                    x_normalized = 1 - (x_mid / img.shape[1])
                    logger.info(f"'{label}': conf={best['confidence']:.2f}, "
                                f"x={x_normalized:.2f}")

                    # Head tracking
                    servo_angle = chase.track_head(x_normalized)

                    # Distance — error if unavailable
                    distance = chase.get_distance(best['bbox'])
                    if distance is None:
                        logger.error(
                            f"No depth for detected object bbox={best['bbox']}")
                        raise RuntimeError(
                            "Depth returned None for detected object. "
                            "Check camera_server depth stream.")

                    logger.info(f"Distance: {distance:.2f}m")
                    action = chase.drive(servo_angle, distance)

                else:
                    chase.stop_tracks()
                    elapsed = chase.time_since_detection()
                    if elapsed > chase.SEARCH_TIMEOUT:
                        chase.search_step()
                        action = "searching"
                    else:
                        logger.info(f"No '{label}' ({elapsed:.1f}s)")

                # Log
                jsonl_file.write(json.dumps({
                    "timestamp": frame_ts,
                    "detections": result['detections'],
                    "target_label": label,
                    "target_bbox": target_bbox,
                    "target_confidence": target_conf,
                    "x_normalized": x_normalized,
                    "distance": distance,
                    "servo_angle": servo_angle,
                    "action": action,
                }) + "\n")
                jsonl_file.flush()

        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            chase.stop_tracks()
            jsonl_file.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='person')
    args = parser.parse_args()

    try:
        chase.init()
    except Exception as e:
        logger.error(f"Init failed: {e}")
        return

    try:
        await run(label=args.label)
    finally:
        chase.shutdown()
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
