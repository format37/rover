"""Main loop: poll detection server, call chase state machine."""
import time
import argparse
import asyncio
import json
import logging
import aiohttp
import chase
from config import (CAMERA_SERVER_URL, DETECTION_SERVER_URL,
                    DETECTION_MAX_AGE_MS, DETECTION_CONFIDENCE_MIN)

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
                # Fetch latest detection from detection server (non-blocking)
                try:
                    async with session.get(f"{DETECTION_SERVER_URL}/detection") as resp:
                        if resp.status != 200:
                            await asyncio.sleep(0.1)
                            continue
                        det_result = await resp.json()
                except Exception as e:
                    logger.warning(f"Detection server fetch failed: {e}")
                    await asyncio.sleep(0.1)
                    continue

                age_ms = (time.time() - det_result['timestamp']) * 1000
                all_detections = det_result['detections'] if age_ms <= DETECTION_MAX_AGE_MS else []
                detections = [d for d in all_detections
                              if d['label'] == label
                              and d['confidence'] >= DETECTION_CONFIDENCE_MIN]

                if detections:
                    best = max(detections, key=lambda d: d['confidence'])
                    x_normalized = best['centroid_x_norm']
                    logger.info(f"'{label}': conf={best['confidence']:.2f}, "
                                f"x={x_normalized:.2f}")
                    result = chase.update(detection=best, x_normalized=x_normalized)
                else:
                    result = chase.update(detection=None, x_normalized=None)

                # Log
                jsonl_file.write(json.dumps({
                    "timestamp": det_result.get('frame_ts', ''),
                    "detections": det_result['detections'],
                    "target_label": label,
                    "target_bbox": detections[0]['bbox'] if detections else None,
                    "target_confidence": detections[0]['confidence'] if detections else None,
                    "x_normalized": detections[0]['centroid_x_norm'] if detections else None,
                    "distance": result.get('distance'),
                    "servo_angle": result.get('servo_angle'),
                    "action": result.get('action'),
                    "state": result.get('state'),
                }) + "\n")
                jsonl_file.flush()

                await asyncio.sleep(0.05)  # cap control loop at ~20fps

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
