#!/usr/bin/env python3
"""Test TRACKING state: drive toward visible target with differential steering.

Requires all 3 servers running (camera, yolo, servo).
A target (--label) must be visible in camera view.

Runs for --duration seconds, logging detections and actions.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                '..', 'object_chaser', 'client'))

import time
import argparse
import asyncio
import json
import logging
import aiohttp
import cv2
import numpy as np
import chase
from config import CAMERA_SERVER_URL, YOLO_URL, DETECTION_CONFIDENCE_MIN

logger = logging.getLogger('test_tracking')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(name)s %(levelname)s %(message)s'))
logger.addHandler(handler)
logging.getLogger('chase').setLevel(logging.INFO)
logging.getLogger('chase').addHandler(handler)


async def run(label, duration):
    import requests

    # Session info
    r = requests.get(f"{CAMERA_SERVER_URL}/session", timeout=2.0)
    info = r.json()
    yolo_dir = info['yolo_dir']
    logger.info(f"Session: {info['session_path']}")
    logger.info(f"Test: TRACKING for {duration}s, target='{label}'")

    jsonl_file = open(f"{yolo_dir}/test_tracking.jsonl", 'a')
    start = time.monotonic()
    frames = 0

    async with aiohttp.ClientSession() as session:
        try:
            while time.monotonic() - start < duration:
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
                    result = chase.update(detection=best,
                                          x_normalized=x_normalized)
                else:
                    result = chase.update(detection=None, x_normalized=None)

                frames += 1
                state = result.get('state', '')
                action = result.get('action', '')
                elapsed = time.monotonic() - start

                jsonl_file.write(json.dumps({
                    "t": round(elapsed, 2),
                    "timestamp": frame_ts,
                    "state": state,
                    "action": action,
                    "detections": len(detections),
                    "distance": result.get('distance'),
                    "servo_angle": result.get('servo_angle'),
                }) + "\n")
                jsonl_file.flush()

                if frames % 30 == 0:
                    logger.info(f"[{elapsed:.0f}s] state={state} action={action} "
                                f"frames={frames}")

        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            chase.shutdown()
            jsonl_file.close()
            logger.info(f"Done: {frames} frames in {time.monotonic()-start:.1f}s")


async def main():
    parser = argparse.ArgumentParser(description='Test TRACKING state')
    parser.add_argument('--label', default='person')
    parser.add_argument('--duration', type=float, default=30.0)
    args = parser.parse_args()

    chase.init()
    await run(args.label, args.duration)


if __name__ == "__main__":
    asyncio.run(main())
