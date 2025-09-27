#!/usr/bin/env python3
"""
Test client for servo control API
"""

import requests
import time
import json

BASE_URL = "http://localhost:8000"

def test_api():
    """Test all API endpoints"""
    print("=== Servo API Test Client ===\n")
    
    try:
        # Test root endpoint
        print("1. Testing root endpoint...")
        response = requests.get(f"{BASE_URL}/")
        print(f"Response: {response.status_code}")
        print(json.dumps(response.json(), indent=2))
        print()
        
        # Test status
        print("2. Getting initial status...")
        response = requests.get(f"{BASE_URL}/status")
        print(json.dumps(response.json(), indent=2))
        print()
        
        # Test movement to different positions
        positions = [0, 90, 180, 45, 135, 90]
        
        for i, angle in enumerate(positions):
            print(f"3.{i+1} Moving to {angle} degrees...")
            response = requests.post(f"{BASE_URL}/move", json={"angle": angle})
            print(json.dumps(response.json(), indent=2))
            time.sleep(1)  # Wait a bit between commands
            
            # Check status
            status_response = requests.get(f"{BASE_URL}/status")
            status = status_response.json()
            print(f"Status: {status['status']} (current: {status['current_position']}°, target: {status['target_position']}°)")
            print()
        
        # Test normalized movement
        print("4. Testing normalized movement (0.25 = 45°)...")
        response = requests.post(f"{BASE_URL}/move_normalized", json={"position": 0.25})
        print(json.dumps(response.json(), indent=2))
        print()
        
        # Test speed change
        print("5. Testing speed change (faster movement)...")
        response = requests.post(f"{BASE_URL}/speed", json={"steps_per_second": 100})
        print(json.dumps(response.json(), indent=2))
        print()
        
        # Test rapid commands (should handle gracefully)
        print("6. Testing rapid position changes...")
        rapid_positions = [0, 180, 0, 180, 90]
        for angle in rapid_positions:
            response = requests.post(f"{BASE_URL}/move", json={"angle": angle})
            print(f"Moving to {angle}°: {response.json()['status']}")
            time.sleep(0.2)  # Very short delay
        print()
        
        # Final status
        print("7. Final status check...")
        time.sleep(2)  # Wait for movement to complete
        response = requests.get(f"{BASE_URL}/status")
        print(json.dumps(response.json(), indent=2))
        
        print("\n=== Test completed successfully! ===")
        
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to API server.")
        print("Make sure the server is running: python3 servo_api.py")
    except Exception as e:
        print(f"Test error: {e}")

def interactive_mode():
    """Interactive mode for manual testing"""
    print("=== Interactive Mode ===")
    print("Commands:")
    print("  angle <0-180>    - Move to specific angle")
    print("  pos <0-1>       - Move to normalized position") 
    print("  speed <1-200>   - Set movement speed")
    print("  status          - Get current status")
    print("  stop            - Stop movement")
    print("  quit            - Exit")
    print()
    
    while True:
        try:
            cmd = input("servo> ").strip().lower()
            
            if cmd == "quit" or cmd == "q":
                break
            elif cmd == "status":
                response = requests.get(f"{BASE_URL}/status")
                print(json.dumps(response.json(), indent=2))
            elif cmd == "stop":
                response = requests.post(f"{BASE_URL}/stop")
                print(json.dumps(response.json(), indent=2))
            elif cmd.startswith("angle "):
                try:
                    angle = float(cmd.split()[1])
                    response = requests.post(f"{BASE_URL}/move", json={"angle": angle})
                    print(json.dumps(response.json(), indent=2))
                except (IndexError, ValueError):
                    print("Usage: angle <0-180>")
            elif cmd.startswith("pos "):
                try:
                    pos = float(cmd.split()[1])
                    response = requests.post(f"{BASE_URL}/move_normalized", json={"position": pos})
                    print(json.dumps(response.json(), indent=2))
                except (IndexError, ValueError):
                    print("Usage: pos <0-1>")
            elif cmd.startswith("speed "):
                try:
                    speed = float(cmd.split()[1])
                    response = requests.post(f"{BASE_URL}/speed", json={"steps_per_second": speed})
                    print(json.dumps(response.json(), indent=2))
                except (IndexError, ValueError):
                    print("Usage: speed <1-200>")
            else:
                print("Unknown command. Type 'quit' to exit.")
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except requests.exceptions.ConnectionError:
            print("Error: Cannot connect to API server")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        interactive_mode()
    else:
        test_api()
