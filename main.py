import os
import sys
import threading

import curses
import random

GRID_WIDTH = 40
GRID_HEIGHT = 20
PLAYER_SYMBOL = 'P'
BORDER_SYMBOL = '#'
EMPTY_SYMBOL = ' '
BATTERY_SYMBOL = 'B'

class Battery:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.energy_boost = 20
        self.collected = False
    
    def collect(self):
        if not self.collected:
            self.collected = True
            return self.energy_boost
        return 0

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
    def __init__(self, num_robots=4, num_batteries=8):
        self.grid = [[EMPTY_SYMBOL for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if x == 0 or x == GRID_WIDTH-1 or y == 0 or y == GRID_HEIGHT-1:
                    self.grid[y][x] = BORDER_SYMBOL
        
        self.robots = []
        self.batteries = []

        # Criar robo do jogador
        player_x, player_y = GRID_WIDTH // 2, GRID_HEIGHT // 2
        player_robot = Robot(0, player_x, player_y, self, is_player=True)
        self.robots.append(player_robot)
        self.grid[player_y][player_x] = PLAYER_SYMBOL

        # Criar robôs adversários
        for i in range(1, num_robots):
            while True:
                x = random.randint(1, GRID_WIDTH-2)
                y = random.randint(1, GRID_HEIGHT-2)
                if self.grid[y][x] == EMPTY_SYMBOL:
                    break
            bot_robot = Robot(i, x, y, self)
            self.robots.append(bot_robot)
            self.grid[y][x] = str(i)

        # Criar baterias
        for _ in range(num_batteries):
            while True:
                x = random.randint(1, GRID_WIDTH-2)
                y = random.randint(1, GRID_HEIGHT-2)
                if self.grid[y][x] == EMPTY_SYMBOL:
                    break
            battery = Battery(x, y)
            self.batteries.append(battery)
            self.grid[y][x] = BATTERY_SYMBOL

        for robot in self.robots:
            robot.start()

    def move_robot(self, robot, dx, dy):
        if robot.status != 'alive':
            return
        new_x = robot.x + dx
        new_y = robot.y + dy
        if (0 < new_x < GRID_WIDTH-1 and 0 < new_y < GRID_HEIGHT-1):
            target_cell = self.grid[new_y][new_x]
            
            if target_cell == EMPTY_SYMBOL or target_cell == BATTERY_SYMBOL:
                if target_cell == BATTERY_SYMBOL:
                    for battery in self.batteries:
                        if battery.x == new_x and battery.y == new_y and not battery.collected:
                            energy_gained = battery.collect()
                            robot.E += energy_gained
                            self.respawn_battery(battery)
                            break
                
                self.grid[robot.y][robot.x] = EMPTY_SYMBOL
                
                robot.x = new_x
                robot.y = new_y
                self.grid[robot.y][robot.x] = PLAYER_SYMBOL if robot.is_player else str(robot.id)

    def get_robot_by_id(self, robot_id):
        for robot in self.robots:
            if robot.id == robot_id:
                return robot
        return None

    def respawn_battery(self, collected_battery):
        while True:
            x = random.randint(1, GRID_WIDTH-2)
            y = random.randint(1, GRID_HEIGHT-2)
            if self.grid[y][x] == EMPTY_SYMBOL:
                break
        
        collected_battery.x = x
        collected_battery.y = y
        collected_battery.collected = False
        self.grid[y][x] = BATTERY_SYMBOL

    def display(self, stdscr):
        stdscr.clear()
        
        max_y, max_x = stdscr.getmaxyx()
        
        for y in range(min(GRID_HEIGHT, max_y - 3)):
            row = ''.join(self.grid[y])
            if len(row) <= max_x - 1:
                stdscr.addstr(y, 0, row)
        
        player_robot = self.robots[0] 
        energy_info = f"Energia do jogador: {player_robot.E}"
        if GRID_HEIGHT + 1 < max_y and len(energy_info) <= max_x - 1:
            stdscr.addstr(GRID_HEIGHT + 1, 0, energy_info)
        
        controls = "Use as setas para mover. Q para sair."
        if GRID_HEIGHT + 2 < max_y and len(controls) <= max_x - 1:
            stdscr.addstr(GRID_HEIGHT + 2, 0, controls)
        
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
