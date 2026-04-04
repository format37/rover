"""Main loop: poll detection server, call chase state machine."""
import time
import asyncio
import json
import logging
from pathlib import Path
import yaml
import aiohttp
import chase
from config import (CAMERA_SERVER_URL, DETECTION_SERVER_URL, DETECTION_MAX_AGE_MS)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logging.getLogger('chase').setLevel(logging.INFO)
logging.getLogger('chase').addHandler(handler)


def load_targets() -> list:
    """Load targets.yaml from repo root. Exits on missing/invalid file."""
    path = Path(__file__).resolve().parent.parent / 'targets.yaml'
    if not path.exists():
        raise FileNotFoundError(f"targets.yaml not found at {path}")
    with open(path) as f:
        cfg = yaml.safe_load(f)
    targets = cfg.get('targets', [])
    if not targets:
        raise ValueError("targets.yaml has no targets defined")
    return targets


def select_target(detections: list, targets: list):
    """Return the best detection to follow, or None.

    Rules:
    1. Keep only detections whose label is in targets and confidence >=
       the per-target threshold.
    2. Among those, choose the highest-priority group (lowest priority number).
    3. Within that group, return the detection with highest confidence.
    """
    target_map = {t['name']: t for t in targets}
    valid = [
        d for d in detections
        if d['label'] in target_map
        and d['confidence'] >= target_map[d['label']]['confidence']
    ]
    if not valid:
        return None
    best_priority = min(target_map[d['label']]['priority'] for d in valid)
    group = [d for d in valid if target_map[d['label']]['priority'] == best_priority]
    return max(group, key=lambda d: d['confidence'])


async def run(targets: list):
    import requests
    labels = [t['name'] for t in sorted(targets, key=lambda t: t['priority'])]
    print(f"Body follow: targets={labels} (priority order, Ctrl+C to stop)")

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
                selected = select_target(all_detections, targets)

                if selected:
                    x_normalized = selected['centroid_x_norm']
                    logger.info(f"'{selected['label']}': conf={selected['confidence']:.2f}, "
                                f"x={x_normalized:.2f}")
                    result = chase.update(detection=selected, x_normalized=x_normalized)
                else:
                    result = chase.update(detection=None, x_normalized=None)

                # Log
                jsonl_file.write(json.dumps({
                    "timestamp": det_result.get('frame_ts', ''),
                    "detections": det_result['detections'],
                    "target_label": selected['label'] if selected else None,
                    "target_bbox": selected['bbox'] if selected else None,
                    "target_confidence": selected['confidence'] if selected else None,
                    "x_normalized": selected['centroid_x_norm'] if selected else None,
                    "distance": result.get('distance'),
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
    try:
        targets = load_targets()
    except Exception as e:
        logger.error(f"Failed to load targets.yaml: {e}")
        return

    try:
        chase.init()
    except Exception as e:
        logger.error(f"Init failed: {e}")
        return

    try:
        await run(targets=targets)
    finally:
        chase.shutdown()
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
