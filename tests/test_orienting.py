#!/usr/bin/env python3
"""Test ORIENTING state: center head then pivot body to face target.

Requires all 3 servers running (camera, yolo, servo).
No target needed for the orient sequence itself.

Steps:
  1. Move servo to --angle (default 135, i.e. 45 deg left of center)
  2. Wait for servo to arrive
  3. Enter ORIENTING state with that detected angle
  4. Chase centering: servo returns to 90, then body pivots
  5. After pivot, enters VERIFYING phase — if target seen -> TRACKING,
     otherwise -> SEARCHING

Runs until state changes to TRACKING or SEARCHING, or --duration expires.
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
from config import (CAMERA_SERVER_URL, YOLO_URL, DETECTION_CONFIDENCE_MIN,
                    SERVO_CENTER)

logger = logging.getLogger('test_orienting')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(name)s %(levelname)s %(message)s'))
logger.addHandler(handler)
logging.getLogger('chase').setLevel(logging.INFO)
logging.getLogger('chase').addHandler(handler)


async def run(label, duration, start_angle):
    import requests

    r = requests.get(f"{CAMERA_SERVER_URL}/session", timeout=2.0)
    info = r.json()
    yolo_dir = info['yolo_dir']
    logger.info(f"Session: {info['session_path']}")
    logger.info(f"Test: ORIENTING from {start_angle}deg (center={SERVO_CENTER})")

    jsonl_file = open(f"{yolo_dir}/test_orienting.jsonl", 'a')
    start = time.monotonic()
    frames = 0

    # Move servo to the off-center angle first
    logger.info(f"Moving servo to {start_angle}deg...")
    requests.post("http://localhost:8000/move",
                  json={"angle": start_angle}, timeout=2.0)

    # Wait for servo to arrive
    for _ in range(50):  # max 5 seconds
        time.sleep(0.1)
        try:
            r = requests.get("http://localhost:8000/status", timeout=0.5)
            if r.status_code == 200 and r.json().get('status') == 'arrived':
                break
        except Exception:
            pass

    logger.info(f"Servo at {start_angle}deg — starting ORIENTING")

    # Force into orienting state
    chase._detected_angle_set(start_angle)
    chase._enter_state(chase.STATE_ORIENTING)
    chase._orient_start()

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
                    "orient_phase": chase._orient_phase,
                    "servo_angle": result.get('servo_angle'),
                    "detections": len(detections),
                }) + "\n")
                jsonl_file.flush()

                logger.info(f"[{elapsed:.1f}s] state={state} phase={chase._orient_phase} "
                            f"action={action}")

                # Stop when orienting is done
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
    parser.add_argument('--angle', type=float, default=135.0,
                        help='Starting servo angle (default 135 = 45deg left)')
    args = parser.parse_args()

    chase.init()
    await run(args.label, args.duration, args.angle)


if __name__ == "__main__":
    asyncio.run(main())
