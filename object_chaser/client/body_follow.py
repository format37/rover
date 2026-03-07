"""Main loop: fetch frames, run YOLO, call chase state machine."""
import time
import argparse
import asyncio
import json
import logging
import aiohttp
import cv2
import numpy as np
import chase
from config import (CAMERA_SERVER_URL, YOLO_URL,
                     DETECTION_CONFIDENCE_MIN)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logging.getLogger('chase').setLevel(logging.INFO)
logging.getLogger('chase').addHandler(handler)


async def run(label='person'):
    import requests
    print(f"Body follow: tracking '{label}' (Ctrl+C to stop)")

    # Session info
    try:
        r = requests.get(f"{CAMERA_SERVER_URL}/session", timeout=2.0)
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
                async with session.get(f"{CAMERA_SERVER_URL}/frame") as resp:
                    if resp.status != 200:
                        await asyncio.sleep(0.1)
                        continue
                    image_data = await resp.read()
                    frame_ts = resp.headers.get('X-Timestamp', '')

# YOLO
                async with session.post(
                        f"{YOLO_URL}/detect/",
                        data={'file': image_data}) as resp:
                    if resp.status != 200:
                        continue
                    yolo_result = await resp.json()

                detections = [d for d in yolo_result['detections']
                              if d['label'] == label
                              and d['confidence'] >= DETECTION_CONFIDENCE_MIN]

                if detections:
                    best = max(detections, key=lambda d: d['confidence'])
                    arr = np.frombuffer(image_data, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    x_mid = best['bbox'][0] + best['bbox'][2] / 2
                    x_normalized = 1 - (x_mid / img.shape[1])
                    logger.info(f"'{label}': conf={best['confidence']:.2f}, "
                                f"x={x_normalized:.2f}")
                    result = chase.update(detection=best,
                                          x_normalized=x_normalized)
                else:
                    result = chase.update(detection=None, x_normalized=None)

                # Log
                jsonl_file.write(json.dumps({
                    "timestamp": frame_ts,
                    "detections": yolo_result['detections'],
                    "target_label": label,
                    "target_bbox": detections[0]['bbox'] if detections else None,
                    "target_confidence": detections[0]['confidence'] if detections else None,
                    "x_normalized": x_normalized if detections else None,
                    "distance": result.get('distance'),
                    "servo_angle": result.get('servo_angle'),
                    "action": result.get('action'),
                    "state": result.get('state'),
                }) + "\n")
                jsonl_file.flush()

        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            chase.shutdown()
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
