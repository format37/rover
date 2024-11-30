from mech_controls import RobotController
import asyncio

async def main():
    robot = RobotController()

    await robot.look_right()
    await robot.look_center(0)
    await robot.look_left()
    await robot.look_center(180)
    
    await robot.move_forward()
    await robot.turn_left()
    await robot.turn_right()
    await robot.move_backward()

if __name__ == '__main__':
    asyncio.run(main())