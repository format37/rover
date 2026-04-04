#!/usr/bin/env python3
"""Test SEARCHING state: body rotates 360° right→left→right scanning for target.

Requires camera, yolo, and track servers running.
No target needed — detections are ignored so the full search sequence runs.

Each sweep is SEARCH_SWEEP_DEG / ROTATION_DEG_PER_SEC seconds long.
Adjust ROTATION_DEG_PER_SEC in config.py to calibrate real vs expected rotation.

Runs for --duration seconds (default 120 to see multiple sweeps).
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
import chase
from config import CAMERA_SERVER_URL

logger = logging.getLogger('test_searching')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(name)s %(levelname)s %(message)s'))
logger.addHandler(handler)
logging.getLogger('chase').setLevel(logging.INFO)
logging.getLogger('chase').addHandler(handler)


async def run(duration):
    import requests

    r = requests.get(f"{CAMERA_SERVER_URL}/session", timeout=2.0)
    info = r.json()
    yolo_dir = info['yolo_dir']
    logger.info(f"Session: {info['session_path']}")
    logger.info(f"Test: SEARCHING for {duration}s")

    jsonl_file = open(f"{yolo_dir}/test_searching.jsonl", 'a')
    start = time.monotonic()
    frames = 0

    # Force directly into SEARCHING state
    chase._enter_state(chase.STATE_SEARCHING)
    chase._search_start()

    async with aiohttp.ClientSession() as session:
        try:
            while time.monotonic() - start < duration:
                async with session.get(f"{CAMERA_SERVER_URL}/frame") as resp:
                    if resp.status != 200:
                        await asyncio.sleep(0.1)
                        continue
                    image_data = await resp.read()
                    frame_ts = resp.headers.get('X-Timestamp', '')

                # Always pass None — we want pure search behavior
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
                    "sweep_index": chase._search_sweep_index,
                }) + "\n")
                jsonl_file.flush()

                if frames % 30 == 0:
                    logger.info(f"[{elapsed:.0f}s] state={state} action={action} "
                                f"sweep={chase._search_sweep_index}")

        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            chase.shutdown()
            jsonl_file.close()
            logger.info(f"Done: {frames} frames in {time.monotonic()-start:.1f}s")


async def main():
    parser = argparse.ArgumentParser(description='Test SEARCHING state')
    parser.add_argument('--duration', type=float, default=120.0)
    args = parser.parse_args()

    chase.init()
    await run(args.duration)


if __name__ == "__main__":
    asyncio.run(main())
