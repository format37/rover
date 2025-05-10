import requests
import logging

def send_goal(goal):
    try:
        # Send GET request to the server
        response = requests.get(f'http://localhost:5000/move', params={'goal': goal})
        response.raise_for_status()  # Raise exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error communicating with server: {str(e)}")
        return {"error": f"Client error: {str(e)}"}

def main():
    # Enable logging
    logging.basicConfig(level=logging.INFO)

    while True:
        try:
            # Get goal input from user
            goal_input = input("Enter goal value (0 to 1, or 'q' to quit): ")
            if goal_input.lower() == 'q':
                logging.info("Exiting client")
                break

            goal = float(goal_input)
            if not 0 <= goal <= 1:
                logging.error("Goal must be between 0 and 1")
                continue

            # Send goal to server
            logging.info(f"Sending goal: {goal}")
            result = send_goal(goal)
            
            # Display response
            if "error" in result:
                logging.error(result["error"])
            else:
                logging.info(f"Success: Head moved to angle {result['angle']:.1f} degrees")

        except ValueError:
            logging.error("Invalid input. Please enter a number between 0 and 1 or 'q' to quit")
        except KeyboardInterrupt:
            logging.info("Exiting client")
            break

if __name__ == '__main__':
    main()