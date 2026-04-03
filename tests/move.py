from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import time
import threading

# Config
target_speed = 0.05   # cruise speed (0.0 – 1.0)
delay = 3             # seconds to hold at cruise speed

STEP_SIZE  = 0.005    # speed delta per tick  (servo_api: step_size = 1.0 deg)
STEP_DELAY = 0.02     # 50 Hz loop            (servo_api: step_delay = 0.02 s)
MIN_SPEED  = 0.01     # minimum effective speed (below this = stopped)

# Motor control mode:
#   'frequency' — vary PWM frequency (step rate) for stepper drivers; hard ceiling ~1526 Hz via PCA9685
#   'duty_cycle' — fixed PWM frequency, vary duty cycle 0-100%; no speed ceiling, suits PWM/DIR drivers
CONTROL_MODE = 'duty_cycle'
PWM_FREQ     = 1000   # fixed PWM frequency for duty_cycle mode (Hz)


class TrackController:
    """Smooth track controller — mirrors ServoController threading pattern."""

    def __init__(self):
        i2c_bus = busio.I2C(SCL, SDA)
        self.pca = [
            PCA9685(i2c_bus, address=0x40),
            PCA9685(i2c_bus, address=0x41),
        ]
        for p in self.pca:
            p.frequency = 60
            p.channels[0].duty_cycle = 0
            p.channels[1].duty_cycle = 0xFFFF

        self.current_speed = 0.0   # what hardware sees right now
        self.goal_speed    = 0.0   # what we want to reach (set by move/stop)
        self.dir0 = 0
        self.dir1 = 1

        self._lock        = threading.Lock()
        self._stop_event  = threading.Event()
        self._thread      = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("Track controller ready")

    # --- hardware ---

    def _set_track(self, track, speed, direction):
        if speed >= MIN_SPEED:
            self.pca[track].channels[1].duty_cycle = int(direction * 0xFFFF)  # DIR
            if CONTROL_MODE == 'duty_cycle':
                # Fixed frequency, duty cycle = speed. No PCA9685 frequency ceiling.
                self.pca[track].frequency              = PWM_FREQ
                self.pca[track].channels[0].duty_cycle = int(speed * 0xFFFF)
            else:
                # Vary frequency as step rate (stepper drivers). Max ~1526 Hz via PCA9685.
                freq = max(24, min(1526, int(speed * 1526)))
                self.pca[track].frequency              = freq
                self.pca[track].channels[0].duty_cycle = 0x7FFF  # 50% step pulses
        else:
            self.pca[track].channels[0].duty_cycle = 0        # stop

    # --- background loop (servo_api._movement_loop equivalent) ---

    def _loop(self):
        while not self._stop_event.is_set():
            with self._lock:
                dist = self.goal_speed - self.current_speed
                if abs(dist) > STEP_SIZE:
                    self.current_speed += STEP_SIZE if dist > 0 else -STEP_SIZE
                else:
                    self.current_speed = self.goal_speed
                spd, d0, d1 = self.current_speed, self.dir0, self.dir1

            self._set_track(0, spd, d0)
            self._set_track(1, spd, d1)
            time.sleep(STEP_DELAY)

    # --- public API ---

    def move(self, dir0, dir1, cruise_speed):
        """Ramp up to cruise_speed in direction (dir0, dir1)."""
        with self._lock:
            self.dir0       = dir0
            self.dir1       = dir1
            self.goal_speed = cruise_speed

    def stop(self):
        """Ramp down to 0."""
        with self._lock:
            self.goal_speed = 0.0

    def wait_stopped(self):
        """Block until ramp-down finishes."""
        while True:
            with self._lock:
                done = self.current_speed == 0.0
            if done:
                break
            time.sleep(STEP_DELAY)

    def shutdown(self):
        self._stop_event.set()
        self._thread.join(timeout=1)
        self._set_track(0, 0, 0)
        self._set_track(1, 0, 0)


# --- main ---

tc = TrackController()
print(f'speed={target_speed}  mode={CONTROL_MODE}  |  w/s/a/d=move  sp=<val>=set speed  x=exit')

cmd = ''
while cmd != 'x':
    cmd = input('cmd: ').strip()

    if cmd in ('w', 's', 'a', 'd'):
        dirs = {
            'w': (0, 1),   # forward
            's': (1, 0),   # backward
            'd': (0, 0),   # rotate left
            'a': (1, 1),   # rotate right
        }
        d0, d1 = dirs[cmd]
        tc.move(d0, d1, target_speed)
        time.sleep(delay)
        tc.stop()
        tc.wait_stopped()
        print('stop')

    elif cmd.startswith('sp='):
        try:
            target_speed = float(cmd[3:])
            print(f'speed={target_speed}')
        except ValueError:
            print('invalid speed')

tc.shutdown()
