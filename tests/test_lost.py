#!/usr/bin/env python3
"""Test LOST state: deceleration after losing target, transition to SEARCHING.

Requires all 3 servers running (camera, yolo, servo).
No target needed — detections are ignored to simulate loss.

Phase 1: Drives forward briefly (--prime seconds) to build speed.
Phase 2: Stops passing detections — observe deceleration and LOST->SEARCHING.

Runs until SEARCHING state is entered or --duration expires.
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

logger = logging.getLogger('test_lost')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(name)s %(levelname)s %(message)s'))
logger.addHandler(handler)
logging.getLogger('chase').setLevel(logging.INFO)
logging.getLogger('chase').addHandler(handler)


async def run(label, duration, prime_seconds):
    import requests

    r = requests.get(f"{CAMERA_SERVER_URL}/session", timeout=2.0)
    info = r.json()
    yolo_dir = info['yolo_dir']
    logger.info(f"Session: {info['session_path']}")
    logger.info(f"Test: LOST (prime={prime_seconds}s, max={duration}s)")

    jsonl_file = open(f"{yolo_dir}/test_lost.jsonl", 'a')
    start = time.monotonic()
    prime_end = start + prime_seconds
    frames = 0
    phase = "priming"

    async with aiohttp.ClientSession() as session:
        try:
            while time.monotonic() - start < duration:
                async with session.get(f"{CAMERA_SERVER_URL}/frame") as resp:
                    if resp.status != 200:
                        await asyncio.sleep(0.1)
                        continue
                    image_data = await resp.read()
                    frame_ts = resp.headers.get('X-Timestamp', '')

                async with session.post(
                        f"{YOLO_URL}/detect/",
                        data={'file': image_data}) as resp:
                    if resp.status != 200:
                        continue
                    yolo_result = await resp.json()

                now = time.monotonic()

                if phase == "priming" and now < prime_end:
                    # During prime phase, pass real detections to build speed
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
                else:
                    if phase == "priming":
                        phase = "lost"
                        logger.info("=== PRIME DONE — simulating target loss ===")
                        # Force into tracking state so the LOST transition happens
                        chase._state = chase.STATE_TRACKING
                        chase._current_speed = chase.SPEED_MAX
                        chase._last_detection_time = time.monotonic()

                    # Always pass None — target is "lost"
                    result = chase.update(detection=None, x_normalized=None)

                frames += 1
                state = result.get('state', '')
                action = result.get('action', '')
                elapsed = now - start

                jsonl_file.write(json.dumps({
                    "t": round(elapsed, 2),
                    "timestamp": frame_ts,
                    "phase": phase,
                    "state": state,
                    "action": action,
                    "speed": chase._current_speed,
                    "servo_angle": result.get('servo_angle'),
                }) + "\n")
                jsonl_file.flush()

                logger.info(f"[{elapsed:.1f}s] phase={phase} state={state} "
                            f"action={action} speed={chase._current_speed:.3f}")

                # Stop once we enter searching
                if state == chase.STATE_SEARCHING:
                    logger.info("=== Reached SEARCHING state — test complete ===")
                    break

        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            chase.shutdown()
            jsonl_file.close()
            logger.info(f"Done: {frames} frames in {time.monotonic()-start:.1f}s")


async def main():
    parser = argparse.ArgumentParser(description='Test LOST state')
    parser.add_argument('--label', default='person')
    parser.add_argument('--duration', type=float, default=30.0)
    parser.add_argument('--prime', type=float, default=3.0,
                        help='Seconds to drive forward before simulating loss')
    args = parser.parse_args()

    chase.init()
    await run(args.label, args.duration, args.prime)


if __name__ == "__main__":
    asyncio.run(main())
