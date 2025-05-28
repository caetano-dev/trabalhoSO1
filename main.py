import os
import sys

import curses
import random

GRID_WIDTH = 40
GRID_HEIGHT = 20
PLAYER_SYMBOL = '🤖'
BORDER_SYMBOL = '#'
EMPTY_SYMBOL = ' '

class Robot:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class Arena:
    def __init__(self):
        self.grid = [[EMPTY_SYMBOL for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if x == 0 or x == GRID_WIDTH-1 or y == 0 or y == GRID_HEIGHT-1:
                    self.grid[y][x] = BORDER_SYMBOL
        self.robot = Robot(GRID_WIDTH // 2, GRID_HEIGHT // 2)
        self.grid[self.robot.y][self.robot.x] = PLAYER_SYMBOL

    def move_robot(self, dx, dy):
        new_x = self.robot.x + dx
        new_y = self.robot.y + dy
        if self.grid[new_y][new_x] == EMPTY_SYMBOL:
            self.grid[self.robot.y][self.robot.x] = EMPTY_SYMBOL
            self.robot.x = new_x
            self.robot.y = new_y
            self.grid[self.robot.y][self.robot.x] = PLAYER_SYMBOL

    def display(self, stdscr):
        for y in range(GRID_HEIGHT):
            row = ''.join(self.grid[y])
            stdscr.addstr(y, 0, row)
        stdscr.refresh()

def main(stdscr):
    arena = Arena()
    stdscr.nodelay(True)
    stdscr.clear()
    while True:
        arena.display(stdscr)
        key = stdscr.getch()
        if key == curses.KEY_UP:
            arena.move_robot(0, -1)
        elif key == curses.KEY_DOWN:
            arena.move_robot(0, 1)
        elif key == curses.KEY_LEFT:
            arena.move_robot(-1, 0)
        elif key == curses.KEY_RIGHT:
            arena.move_robot(1, 0)
        elif key == ord('q'):
            break
        curses.napms(50)

if __name__ == "__main__":
    curses.wrapper(main)
