import os
import sys
import threading
import multiprocessing
import queue
import time

import curses
import random

GRID_WIDTH = 40
GRID_HEIGHT = 20
PLAYER_SYMBOL = 'P'
BORDER_SYMBOL = '#'
EMPTY_SYMBOL = ' '
BATTERY_SYMBOL = 'B'
ENERGY_LIMIT = 100

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

class Robot(multiprocessing.Process):
    def __init__(self, robot_id, x, y, is_player=False, command_queue=None, response_queue=None):
        super().__init__()
        self.id = robot_id
        self.x = x
        self.y = y
        self.is_player = is_player
        self.command_queue = command_queue
        self.response_queue = response_queue

        self.F = random.randint(1, 10)  # Força
        self.E = random.randint(10, 100)  # Energia
        self.V = random.randint(1, 5)  # Velocidade
        self.status = 'alive'  # or 'dead'

        self.direction = (0, 0)
        self.running = True
        # Note: threading.Lock will be created in run() method to avoid pickling issues

    def housekeeping(self):
        while self.running and self.status == 'alive':
            try:
                with self.energy_lock:
                    # Consome energia baseado na velocidade e força do robô
                    energy_consumption = max(1, (self.V + self.F) // 4)
                    self.E = max(0, self.E - energy_consumption)
                    
                    # Se a energia acabar, o robô morre
                    if self.E <= 0:
                        self.status = 'dead'
                        # Notifica o processo principal sobre a morte do robô
                        death_notification = {
                            'type': 'robot_death',
                            'robot_id': self.id
                        }
                        self.response_queue.put(death_notification)
                        break
                
                # Pausa de 1 segundo entre atualizações de energia
                time.sleep(1.0)
            except:
                break

    def set_direction(self, dx, dy):
        self.direction = (dx, dy)

    def run(self):
        self.energy_lock = threading.Lock()
        
        housekeeping_thread = threading.Thread(target=self.housekeeping, daemon=True)
        housekeeping_thread.start()
        
        while self.running and self.status == 'alive':
            try:
                # pega comandos do processo principal
                try:
                    command = self.command_queue.get_nowait()
                    if command['type'] == 'stop':
                        self.running = False
                        break
                    elif command['type'] == 'set_direction':
                        self.direction = (command['dx'], command['dy'])
                    elif command['type'] == 'update_position':
                        self.x = command['x']
                        self.y = command['y']
                    elif command['type'] == 'update_energy':
                        with self.energy_lock:
                            self.E = command['energy']
                except queue.Empty:
                    pass

                if self.is_player:
                    dx, dy = self.direction
                    if dx != 0 or dy != 0:
                        # manda comandos para mover
                        move_request = {
                            'type': 'move_request',
                            'robot_id': self.id,
                            'dx': dx,
                            'dy': dy
                        }
                        self.response_queue.put(move_request)
                        self.direction = (0, 0)
                else:
                    for _ in range(self.V):
                        dx, dy = random.choice([(0,1),(0,-1),(1,0),(-1,0)])
                        move_request = {
                            'type': 'move_request',
                            'robot_id': self.id,
                            'dx': dx,
                            'dy': dy
                        }
                        self.response_queue.put(move_request)
                        time.sleep(0.05)
                
                time.sleep(0.05)
            except KeyboardInterrupt:
                break

class Arena:
    def __init__(self, num_robots=4, num_batteries=8):
        self.grid = [[EMPTY_SYMBOL for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if x == 0 or x == GRID_WIDTH-1 or y == 0 or y == GRID_HEIGHT-1:
                    self.grid[y][x] = BORDER_SYMBOL
        
        self.robots = []
        self.robot_processes = []
        self.robot_data = {}  
        self.batteries = []
        
        self.command_queues = {}
        self.response_queue = multiprocessing.Queue()

        # Criar robo do jogador
        player_x, player_y = GRID_WIDTH // 2, GRID_HEIGHT // 2
        player_command_queue = multiprocessing.Queue()
        self.command_queues[0] = player_command_queue
        
        player_robot = Robot(0, player_x, player_y, is_player=True, 
                           command_queue=player_command_queue, 
                           response_queue=self.response_queue)
        self.robot_processes.append(player_robot)
        self.robot_data[0] = {
            'x': player_x, 'y': player_y, 'E': player_robot.E, 
            'F': player_robot.F, 'V': player_robot.V, 'status': 'alive', 'is_player': True
        }
        self.grid[player_y][player_x] = PLAYER_SYMBOL

        # Criar robôs adversários
        for i in range(1, num_robots):
            while True:
                x = random.randint(1, GRID_WIDTH-2)
                y = random.randint(1, GRID_HEIGHT-2)
                if self.grid[y][x] == EMPTY_SYMBOL:
                    break
            
            command_queue = multiprocessing.Queue()
            self.command_queues[i] = command_queue
            
            bot_robot = Robot(i, x, y, is_player=False,
                            command_queue=command_queue,
                            response_queue=self.response_queue)
            self.robot_processes.append(bot_robot)
            self.robot_data[i] = {
                'x': x, 'y': y, 'E': bot_robot.E, 
                'F': bot_robot.F, 'V': bot_robot.V, 'status': 'alive', 'is_player': False
            }
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

        for robot_process in self.robot_processes:
            robot_process.start()

    def process_robot_messages(self):
        try:
            while True:
                try:
                    message = self.response_queue.get_nowait()
                    if message['type'] == 'move_request':
                        robot_id = message['robot_id']
                        dx, dy = message['dx'], message['dy']
                        self.move_robot(robot_id, dx, dy)
                    elif message['type'] == 'robot_death':
                        robot_id = message['robot_id']
                        self.handle_robot_death(robot_id)
                except queue.Empty:
                    break
        except:
            pass

    def handle_robot_death(self, robot_id):
        robot_data = self.robot_data[robot_id]
        robot_data['status'] = 'dead'
        
        # Remove o robô do grid
        old_x, old_y = robot_data['x'], robot_data['y']
        self.grid[old_y][old_x] = EMPTY_SYMBOL

    def move_robot(self, robot_id, dx, dy):
        robot_data = self.robot_data[robot_id]
        if robot_data['status'] != 'alive':
            return
            
        old_x, old_y = robot_data['x'], robot_data['y']
        new_x = old_x + dx
        new_y = old_y + dy
        
        if (0 < new_x < GRID_WIDTH-1 and 0 < new_y < GRID_HEIGHT-1):
            target_cell = self.grid[new_y][new_x]
            
            if target_cell == EMPTY_SYMBOL or target_cell == BATTERY_SYMBOL:
                if target_cell == BATTERY_SYMBOL:
                    for battery in self.batteries:
                        if battery.x == new_x and battery.y == new_y and not battery.collected:
                            energy_gained = battery.collect()
                            if energy_gained > 0:
                                robot_data['E'] += energy_gained
                                if robot_data['E'] > ENERGY_LIMIT:
                                    robot_data['E'] = ENERGY_LIMIT
                            # atualiza energia do robô
                            self.command_queues[robot_id].put({
                                'type': 'update_energy',
                                'energy': robot_data['E']
                            })
                            self.respawn_battery(battery)
                            break
                
                self.grid[old_y][old_x] = EMPTY_SYMBOL
                
                robot_data['x'] = new_x
                robot_data['y'] = new_y
                
                self.command_queues[robot_id].put({
                    'type': 'update_position',
                    'x': new_x,
                    'y': new_y
                })
                
                self.grid[new_y][new_x] = PLAYER_SYMBOL if robot_data['is_player'] else str(robot_id)

    def set_player_direction(self, dx, dy):
        self.command_queues[0].put({
            'type': 'set_direction',
            'dx': dx,
            'dy': dy
        })

    def get_robot_by_id(self, robot_id):
        return self.robot_data.get(robot_id)

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
        
        player_data = self.robot_data[0] 
        energy_info = f"Energia do jogador: {player_data['E']} | Status: {player_data['status']}"
        if GRID_HEIGHT + 1 < max_y and len(energy_info) <= max_x - 1:
            stdscr.addstr(GRID_HEIGHT + 1, 0, energy_info)
        
        alive_robots = sum(1 for robot_data in self.robot_data.values() if robot_data['status'] == 'alive')
        status_info = f"Robôs vivos: {alive_robots}/{len(self.robot_data)}"
        if GRID_HEIGHT + 2 < max_y and len(status_info) <= max_x - 1:
            stdscr.addstr(GRID_HEIGHT + 2, 0, status_info)
        
        controls = "Use as setas para mover. Q para sair."
        if GRID_HEIGHT + 3 < max_y and len(controls) <= max_x - 1:
            stdscr.addstr(GRID_HEIGHT + 3, 0, controls)
        
        stdscr.refresh()

    def cleanup(self):
        for robot_id in self.command_queues:
            self.command_queues[robot_id].put({'type': 'stop'})
        
        for process in self.robot_processes:
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()

def main(stdscr):
    arena = Arena(num_robots=5) 
    stdscr.nodelay(True)
    stdscr.clear()
    try:
        while True:
            arena.process_robot_messages()
            
            arena.display(stdscr)
            
            key = stdscr.getch()
            if key == curses.KEY_UP:
                arena.set_player_direction(0, -1)
            elif key == curses.KEY_DOWN:
                arena.set_player_direction(0, 1)
            elif key == curses.KEY_LEFT:
                arena.set_player_direction(-1, 0)
            elif key == curses.KEY_RIGHT:
                arena.set_player_direction(1, 0)
            elif key == ord('q'):
                break
            curses.napms(50)
    finally:
        arena.cleanup()

if __name__ == "__main__":
    # para macos ou windows
    multiprocessing.set_start_method('spawn', force=True)
    curses.wrapper(main)
