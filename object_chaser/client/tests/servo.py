#!/usr/bin/env python3
"""
Simple servo hardware test - no async, no threading, no complexity.
This should work if your hardware is properly connected.
"""

import time
from adafruit_servokit import ServoKit

def test_servo_basic():
    """Basic servo movement test"""
    print("Initializing ServoKit...")
    
    # Initialize the servo controller
    kit = ServoKit(channels=16, address=0x42)
    servo = kit.servo[0]  # Using channel 0
    
    print("Starting basic servo test...")
    print("Servo should move between positions with 2-second pauses")
    
    try:
        # Test sequence: move to different positions with delays
        positions = [90, 0, 180, 90, 45, 135, 90]
        
        for i, angle in enumerate(positions):
            print(f"Step {i+1}: Moving to {angle} degrees")
            servo.angle = angle
            time.sleep(2.0)  # Wait 2 seconds between movements
            
        print("Basic test completed successfully!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        return False
    
    return True

def test_servo_sweep():
    """Continuous sweep test"""
    print("\nStarting sweep test...")
    print("Servo should sweep back and forth 3 times")
    
    kit = ServoKit(channels=16, address=0x42)
    servo = kit.servo[0]
    
    try:
        for cycle in range(3):
            print(f"Sweep cycle {cycle + 1}/3")
            
            # Sweep from 0 to 180
            for angle in range(0, 181, 10):
                servo.angle = angle
                time.sleep(0.05)  # Small delay for smooth movement
            
            time.sleep(0.5)  # Pause at 180
            
            # Sweep from 180 back to 0
            for angle in range(180, -1, -10):
                servo.angle = angle
                time.sleep(0.05)
            
            time.sleep(0.5)  # Pause at 0
            
        # Return to center
        servo.angle = 90
        print("Sweep test completed!")
        
    except Exception as e:
        print(f"Error during sweep: {e}")
        return False
    
    return True

def main():
    print("=== Servo Hardware Test ===")
    print("Make sure your servo is connected to channel 0")
    print("Press Ctrl+C to stop at any time\n")
    
    try:
        # Run basic position test
        if not test_servo_basic():
            print("Basic test failed - check connections")
            return
        
        # Ask user if they want to continue
        input("\nPress Enter to run sweep test (or Ctrl+C to exit)...")
        
        # Run sweep test
        if not test_servo_sweep():
            print("Sweep test failed")
            return
            
        print("\n=== All tests completed successfully! ===")
        print("Your servo hardware appears to be working correctly.")
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        print("Check your wiring and servo connections")

if __name__ == "__main__":
    main()
