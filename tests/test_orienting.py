#!/usr/bin/env python3
"""Test ORIENTING state: rotate body to face a detected object.

Requires camera, yolo, and track servers running.

Steps:
  1. Enter ORIENTING with --angle degrees offset (positive = right of center).
  2. Body rotates to center the target (time-based, duration = angle / ROTATION_DEG_PER_SEC).
  3. Enters VERIFYING phase — if target seen in frame -> TRACKING, else -> SEARCHING.

Use --angle to simulate different off-center positions:
  45.0  = target 45° to the right → rover should rotate right
  -45.0 = target 45° to the left  → rover should rotate left

Runs until state changes to TRACKING or SEARCHING, or --duration expires.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'client'))

import time
import argparse
import asyncio
import json
import logging
import aiohttp
import cv2
import numpy as np
import chase
from config import (CAMERA_SERVER_URL, YOLO_URL, DETECTION_CONFIDENCE_MIN)

logger = logging.getLogger('test_orienting')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(name)s %(levelname)s %(message)s'))
logger.addHandler(handler)
logging.getLogger('chase').setLevel(logging.INFO)
logging.getLogger('chase').addHandler(handler)


async def run(label, duration, angle_offset):
    import requests

    r = requests.get(f"{CAMERA_SERVER_URL}/session", timeout=2.0)
    info = r.json()
    yolo_dir = info['yolo_dir']
    logger.info(f"Session: {info['session_path']}")
    logger.info(f"Test: ORIENTING with angle_offset={angle_offset:+.1f}deg")

    jsonl_file = open(f"{yolo_dir}/test_orienting.jsonl", 'a')
    start = time.monotonic()
    frames = 0

    # Force into orienting state with the given angle offset
    chase._enter_state(chase.STATE_ORIENTING)
    chase._orient_start(angle_offset)

    async with aiohttp.ClientSession() as session:
        try:
            while time.monotonic() - start < duration:
                async with session.get(f"{CAMERA_SERVER_URL}/frame") as resp:
                    if resp.status != 200:
                        await asyncio.sleep(0.1)
                        continue
                    image_data = await resp.read()
                    frame_ts = resp.headers.get('X-Timestamp', '')

                # Run YOLO to check for target (needed for verify phase)
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
                    result = chase.update(detection=best, x_normalized=x_normalized)
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
                    "orient_phase": chase._orient_phase,
                    "detections": len(detections),
                }) + "\n")
                jsonl_file.flush()

                logger.info(f"[{elapsed:.1f}s] state={state} phase={chase._orient_phase} "
                            f"action={action}")

                if state in (chase.STATE_TRACKING, chase.STATE_SEARCHING):
                    logger.info(f"=== ORIENTING complete -> {state} ===")
                    break

        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            chase.shutdown()
            jsonl_file.close()
            logger.info(f"Done: {frames} frames in {time.monotonic()-start:.1f}s")


async def main():
    parser = argparse.ArgumentParser(description='Test ORIENTING state')
    parser.add_argument('--label', default='person')
    parser.add_argument('--duration', type=float, default=30.0)
    parser.add_argument('--angle', type=float, default=45.0,
                        help='Angle offset in degrees: positive=right, negative=left')
    args = parser.parse_args()

    chase.init()
    await run(args.label, args.duration, args.angle)


if __name__ == "__main__":
    asyncio.run(main())
