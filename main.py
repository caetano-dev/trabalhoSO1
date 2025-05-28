import os
import sys
import threading

import curses
import random

GRID_WIDTH = 40
GRID_HEIGHT = 20
PLAYER_SYMBOL = '🤖'
BORDER_SYMBOL = '#'
EMPTY_SYMBOL = ' '

class Robot(threading.Thread):
    def __init__(self, robot_id, x, y, arena, is_player=False):
        super().__init__()
        self.id = robot_id
        self.x = x
        self.y = y
        self.arena = arena
        self.is_player = is_player

        self.F = random.randint(1, 10)  # Força
        self.E = random.randint(10, 100)  # Energia
        self.V = random.randint(1, 5)  # Velocidade
        self.status = 'alive'  # or 'dead'

        self.direction = (0, 0)
        self.running = True
        self.lock = threading.Lock()

    def set_direction(self, dx, dy):
        with self.lock:
            self.direction = (dx, dy)

    def run(self):
        while self.running and self.status == 'alive':
            if self.is_player:
                with self.lock:
                    dx, dy = self.direction
                if dx != 0 or dy != 0:
                    self.arena.move_robot(self, dx, dy)
                    self.set_direction(0, 0)
            else:
                for _ in range(self.V):
                    dx, dy = random.choice([(0,1),(0,-1),(1,0),(-1,0)])
                    self.arena.move_robot(self, dx, dy)
                    threading.Event().wait(0.05)
            threading.Event().wait(0.05)

class Arena:
    def __init__(self, num_robots=4):
        self.grid = [[EMPTY_SYMBOL for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if x == 0 or x == GRID_WIDTH-1 or y == 0 or y == GRID_HEIGHT-1:
                    self.grid[y][x] = BORDER_SYMBOL
        self.robots = []
        player_x, player_y = GRID_WIDTH // 2, GRID_HEIGHT // 2
        player_robot = Robot(0, player_x, player_y, self, is_player=True)
        self.robots.append(player_robot)
        self.grid[player_y][player_x] = PLAYER_SYMBOL
        for i in range(1, num_robots):
            while True:
                x = random.randint(1, GRID_WIDTH-2)
                y = random.randint(1, GRID_HEIGHT-2)
                if self.grid[y][x] == EMPTY_SYMBOL:
                    break
            bot_robot = Robot(i, x, y, self)
            self.robots.append(bot_robot)
            self.grid[y][x] = str(i)

        for robot in self.robots:
            robot.start()

    def move_robot(self, robot, dx, dy):
        if robot.status != 'alive':
            return
        new_x = robot.x + dx
        new_y = robot.y + dy
        if (0 < new_x < GRID_WIDTH-1 and 0 < new_y < GRID_HEIGHT-1 and
            self.grid[new_y][new_x] == EMPTY_SYMBOL):
            self.grid[robot.y][robot.x] = EMPTY_SYMBOL
            robot.x = new_x
            robot.y = new_y
            self.grid[robot.y][robot.x] = PLAYER_SYMBOL if robot.is_player else str(robot.id)

    def display(self, stdscr):
        for y in range(GRID_HEIGHT):
            row = ''.join(self.grid[y])
            stdscr.addstr(y, 0, row)
        stdscr.refresh()

def main(stdscr):
    arena = Arena(num_robots=5) 
    stdscr.nodelay(True)
    stdscr.clear()
    try:
        while True:
            arena.display(stdscr)
            key = stdscr.getch()
            if key == curses.KEY_UP:
                arena.robots[0].set_direction(0, -1)
            elif key == curses.KEY_DOWN:
                arena.robots[0].set_direction(0, 1)
            elif key == curses.KEY_LEFT:
                arena.robots[0].set_direction(-1, 0)
            elif key == curses.KEY_RIGHT:
                arena.robots[0].set_direction(1, 0)
            elif key == ord('q'):
                break
            curses.napms(50)
    finally:
        for robot in arena.robots:
            robot.running = False
        for robot in arena.robots:
            robot.join()

if __name__ == "__main__":
    curses.wrapper(main)
