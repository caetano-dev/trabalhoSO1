import sys
import threading
import multiprocessing
import multiprocessing.shared_memory
import time
import ctypes
import struct
import curses
import random

# Global manager for shared locks
_manager = None
_shared_locks = None

def get_shared_locks():
    """Get or create shared locks using multiprocessing.Manager"""
    global _manager, _shared_locks
    if _shared_locks is None:
        _manager = multiprocessing.Manager()
        _shared_locks = {
            'init_mutex': _manager.Lock(),
            'grid_mutex': _manager.Lock(),
            'robots_mutex': _manager.Lock(),
            'battery_mutexes': [_manager.Lock() for _ in range(20)]  # MAX_BATTERIES
        }
    return _shared_locks

GRID_WIDTH = 40
GRID_HEIGHT = 20
PLAYER_SYMBOL = 'P'
BORDER_SYMBOL = '#'
EMPTY_SYMBOL = ' '
BATTERY_SYMBOL = 'B'
ENERGY_LIMIT = 100
MAX_ROBOTS = 8
MAX_BATTERIES = 20

# Shared memory structure offsets
GRID_OFFSET = 0
GRID_SIZE = GRID_WIDTH * GRID_HEIGHT
ROBOTS_OFFSET = GRID_SIZE
ROBOT_SIZE = 32  # id(4) + x(4) + y(4) + F(4) + E(4) + V(4) + status(4) + padding(4)
ROBOTS_SIZE = MAX_ROBOTS * ROBOT_SIZE
BATTERIES_OFFSET = ROBOTS_OFFSET + ROBOTS_SIZE
BATTERY_SIZE = 16  # x(4) + y(4) + collected(4) + owner(4)
BATTERIES_SIZE = MAX_BATTERIES * BATTERY_SIZE
FLAGS_OFFSET = BATTERIES_OFFSET + BATTERIES_SIZE
FLAGS_SIZE = 32  # init_done(4) + game_over(4) + winner(4) + alive_count(4) + etc
TOTAL_SHARED_SIZE = FLAGS_OFFSET + FLAGS_SIZE

class SharedGameState:
    """Manages shared memory and synchronization primitives for the robot arena"""
    
    def __init__(self, create=True, shared_memory_name='robot_arena_shm', shared_locks=None):
        self.shared_memory_name = shared_memory_name
        
        if create:
            # Create shared memory block
            try:
                # Try to clean up any existing shared memory first
                try:
                    existing_shm = multiprocessing.shared_memory.SharedMemory(
                        name=shared_memory_name, create=False
                    )
                    existing_shm.close()
                    existing_shm.unlink()
                except:
                    pass
                
                self.shm = multiprocessing.shared_memory.SharedMemory(
                    name=shared_memory_name, 
                    create=True, 
                    size=TOTAL_SHARED_SIZE
                )
            except FileExistsError:
                # If it already exists, attach to it
                self.shm = multiprocessing.shared_memory.SharedMemory(
                    name=shared_memory_name, 
                    create=False
                )
        else:
            # Attach to existing shared memory
            self.shm = multiprocessing.shared_memory.SharedMemory(
                name=shared_memory_name, 
                create=False
            )
        
        # Create memory view as ctypes array
        self.memory = (ctypes.c_ubyte * TOTAL_SHARED_SIZE).from_buffer(self.shm.buf)
        
        # Use shared locks if provided, otherwise create new ones
        if shared_locks:
            self.init_mutex = shared_locks['init_mutex']
            self.grid_mutex = shared_locks['grid_mutex']
            self.robots_mutex = shared_locks['robots_mutex']
            self.battery_mutexes = shared_locks['battery_mutexes']
        else:
            # Create fresh locks (this will only work in the main process)
            locks = get_shared_locks()
            self.init_mutex = locks['init_mutex']
            self.grid_mutex = locks['grid_mutex']
            self.robots_mutex = locks['robots_mutex']
            self.battery_mutexes = locks['battery_mutexes']
        
        if create:
            self._initialize_memory()
    
    def _initialize_memory(self):
        """Initialize shared memory with default values"""
        # Clear all memory
        for i in range(TOTAL_SHARED_SIZE):
            self.memory[i] = 0
        
        # Initialize grid with borders
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                offset = GRID_OFFSET + y * GRID_WIDTH + x
                if x == 0 or x == GRID_WIDTH-1 or y == 0 or y == GRID_HEIGHT-1:
                    self.memory[offset] = ord(BORDER_SYMBOL)
                else:
                    self.memory[offset] = ord(EMPTY_SYMBOL)
    
    def get_grid_cell(self, x, y):
        """Get grid cell value (thread-safe read)"""
        if 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT:
            offset = GRID_OFFSET + y * GRID_WIDTH + x
            return chr(self.memory[offset])
        return BORDER_SYMBOL
    
    def set_grid_cell(self, x, y, value):
        """Set grid cell value (requires grid_mutex)"""
        if 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT:
            offset = GRID_OFFSET + y * GRID_WIDTH + x
            self.memory[offset] = ord(str(value)[0])
    
    def get_robot_data(self, robot_id):
        """Get robot data structure (requires robots_mutex for writing)"""
        if 0 <= robot_id < MAX_ROBOTS:
            offset = ROBOTS_OFFSET + robot_id * ROBOT_SIZE
            # Unpack robot data: id, x, y, F, E, V, status, padding
            data = struct.unpack('8i', bytes(self.memory[offset:offset+32]))
            return {
                'id': data[0], 'x': data[1], 'y': data[2],
                'F': data[3], 'E': data[4], 'V': data[5], 
                'status': data[6]  # 0=dead, 1=alive
            }
        return None
    
    def set_robot_data(self, robot_id, robot_data):
        """Set robot data structure (requires robots_mutex)"""
        if 0 <= robot_id < MAX_ROBOTS:
            offset = ROBOTS_OFFSET + robot_id * ROBOT_SIZE
            # Pack robot data: id, x, y, F, E, V, status, padding
            data = struct.pack('8i', 
                robot_data['id'], robot_data['x'], robot_data['y'],
                robot_data['F'], robot_data['E'], robot_data['V'],
                robot_data['status'], 0  # padding
            )
            self.memory[offset:offset+32] = data
    
    def get_battery_data(self, battery_id):
        """Get battery data structure (requires battery_mutex for writing)"""
        if 0 <= battery_id < MAX_BATTERIES:
            offset = BATTERIES_OFFSET + battery_id * BATTERY_SIZE
            # Unpack: x, y, collected, owner
            data = struct.unpack('4i', bytes(self.memory[offset:offset+16]))
            return {
                'x': data[0], 'y': data[1], 
                'collected': data[2], 'owner': data[3]
            }
        return None
    
    def set_battery_data(self, battery_id, battery_data):
        """Set battery data structure (requires battery_mutex)"""
        if 0 <= battery_id < MAX_BATTERIES:
            offset = BATTERIES_OFFSET + battery_id * BATTERY_SIZE
            data = struct.pack('4i',
                battery_data['x'], battery_data['y'],
                battery_data['collected'], battery_data['owner']
            )
            self.memory[offset:offset+16] = data
    
    def get_flags(self):
        """Get game flags"""
        offset = FLAGS_OFFSET
        data = struct.unpack('8i', bytes(self.memory[offset:offset+32]))
        return {
            'init_done': data[0], 'game_over': data[1],
            'winner': data[2], 'alive_count': data[3]
        }
    
    def set_flags(self, flags):
        """Set game flags"""
        offset = FLAGS_OFFSET
        data = struct.pack('8i',
            flags.get('init_done', 0), flags.get('game_over', 0),
            flags.get('winner', -1), flags.get('alive_count', 0),
            0, 0, 0, 0  # padding
        )
        self.memory[offset:offset+32] = data
    
    def cleanup(self):
        """Clean up shared memory"""
        try:
            self.shm.close()
            self.shm.unlink()
        except:
            pass

class Battery:
    def __init__(self, x, y, battery_id, shared_state):
        self.id = battery_id
        self.shared_state = shared_state
        
        # Initialize in shared memory
        with self.shared_state.battery_mutexes[battery_id]:
            self.shared_state.set_battery_data(battery_id, {
                'x': x, 'y': y, 'collected': 0, 'owner': -1
            })
    
    def try_collect(self, robot_id):
        """Try to collect battery (returns energy gained)"""
        with self.shared_state.battery_mutexes[self.id]:
            battery_data = self.shared_state.get_battery_data(self.id)
            if battery_data and battery_data['collected'] == 0:
                # Mark as collected by this robot
                battery_data['collected'] = 1
                battery_data['owner'] = robot_id
                self.shared_state.set_battery_data(self.id, battery_data)
                return 20
        return 0

class Robot(multiprocessing.Process):
    """Robot process with shared memory access and proper mutex usage"""
    
    def __init__(self, robot_id, x, y, is_player=False, shared_memory_name='robot_arena_shm', shared_locks=None):
        super().__init__()
        self.id = robot_id
        self.is_player = is_player
        self.running = True
        self.shared_memory_name = shared_memory_name
        self.shared_locks = shared_locks
        
        # Robot stats (will be stored in shared memory)
        self.F = random.randint(1, 10)  # Força
        self.E = random.randint(60, 100)  # Energia  
        self.V = random.randint(1, 5)  # Velocidade
        
        # Player control
        self.direction_queue = multiprocessing.Queue() if is_player else None
        
        # Will attach to shared memory in run()
        self.shared_state = None
    
    def attach_shared_memory(self):
        """Attach to existing shared memory"""
        self.shared_state = SharedGameState(create=False, shared_memory_name=self.shared_memory_name, shared_locks=self.shared_locks)
    
    def sense_act(self):
        """Main sense-act loop following the documented procedure"""
        while self.running:
            try:
                # 1. Take snapshot of grid (without lock - just reading)
                grid_snapshot = self.take_grid_snapshot()
                robot_data = None
                
                with self.shared_state.robots_mutex:
                    robot_data = self.shared_state.get_robot_data(self.id)
                
                if not robot_data or robot_data['status'] == 0:  # dead
                    break
                
                # 2. Decide action based on snapshot
                actions = self.decide_actions(grid_snapshot, robot_data)
                
                # 3. Execute each action with proper lock ordering
                for action in actions:
                    self.execute_action(action, robot_data)
                    
                    # Refresh robot data after each action
                    with self.shared_state.robots_mutex:
                        robot_data = self.shared_state.get_robot_data(self.id)
                        if robot_data['status'] == 0:  # died during action
                            return
                
                time.sleep(0.1)  # Small delay between action cycles
                
            except Exception as e:
                print(f"Robot {self.id} error in sense_act: {e}")
                break
    
    def take_grid_snapshot(self):
        """Take a snapshot of the grid for decision making"""
        snapshot = []
        for y in range(GRID_HEIGHT):
            row = []
            for x in range(GRID_WIDTH):
                row.append(self.shared_state.get_grid_cell(x, y))
            snapshot.append(row)
        return snapshot
    
    def decide_actions(self, grid_snapshot, robot_data):
        """Decide what actions to take based on grid snapshot"""
        actions = []
        
        if self.is_player:
            # Player robot: check for direction commands
            try:
                direction = self.direction_queue.get_nowait()
                dx, dy = direction
                actions.append(('move', dx, dy))
            except:
                pass  # No command, no action
        else:
            # AI robot: make V movement attempts
            for _ in range(robot_data['V']):
                dx, dy = random.choice([(0,1), (0,-1), (1,0), (-1,0), (0,0)])
                actions.append(('move', dx, dy))
        
        return actions
    
    def execute_action(self, action, robot_data):
        """Execute an action with proper lock ordering"""
        if action[0] == 'move':
            _, dx, dy = action
            self.try_move(dx, dy, robot_data)
    
    def try_move(self, dx, dy, robot_data):
        """Try to move robot (handles dueling, battery collection, etc.)"""
        old_x, old_y = robot_data['x'], robot_data['y']
        new_x, new_y = old_x + dx, old_y + dy
        
        # Check bounds
        if not (0 < new_x < GRID_WIDTH-1 and 0 < new_y < GRID_HEIGHT-1):
            return
        
        # Follow lock ordering: grid_mutex -> robots_mutex -> battery_mutexes
        with self.shared_state.grid_mutex:
            target_cell = self.shared_state.get_grid_cell(new_x, new_y)
            
            if target_cell == EMPTY_SYMBOL:
                # Simple move
                self.perform_move(old_x, old_y, new_x, new_y)
                
            elif target_cell == BATTERY_SYMBOL:
                # Try to collect battery
                self.try_collect_battery(old_x, old_y, new_x, new_y)
                
            elif target_cell.isdigit() or target_cell == PLAYER_SYMBOL:
                # Another robot - DUEL!
                other_robot_id = self.find_robot_at_position(new_x, new_y)
                if other_robot_id is not None and other_robot_id != self.id:
                    self.initiate_duel(other_robot_id, old_x, old_y, new_x, new_y)
    
    def perform_move(self, old_x, old_y, new_x, new_y):
        """Perform a simple move (grid_mutex already held)"""
        with self.shared_state.robots_mutex:
            # Update robot position
            robot_data = self.shared_state.get_robot_data(self.id)
            robot_data['x'] = new_x
            robot_data['y'] = new_y
            robot_data['E'] = max(0, robot_data['E'] - 1)  # Movement costs 1 energy
            
            # Check if robot dies from energy loss
            if robot_data['E'] <= 0:
                robot_data['status'] = 0  # dead
                self.shared_state.set_robot_data(self.id, robot_data)
                self.shared_state.set_grid_cell(old_x, old_y, EMPTY_SYMBOL)
                return
            
            self.shared_state.set_robot_data(self.id, robot_data)
        
        # Update grid (grid_mutex still held)
        self.shared_state.set_grid_cell(old_x, old_y, EMPTY_SYMBOL)
        symbol = PLAYER_SYMBOL if self.is_player else str(self.id)
        self.shared_state.set_grid_cell(new_x, new_y, symbol)
    
    def try_collect_battery(self, old_x, old_y, new_x, new_y):
        """Try to collect battery at target position"""
        battery_id = self.find_battery_at_position(new_x, new_y)
        if battery_id is not None:
            # Try to collect the specific battery (with its mutex)
            energy_gained = 0
            with self.shared_state.battery_mutexes[battery_id]:
                battery_data = self.shared_state.get_battery_data(battery_id)
                if battery_data and battery_data['collected'] == 0:
                    # Collect battery
                    battery_data['collected'] = 1
                    battery_data['owner'] = self.id
                    self.shared_state.set_battery_data(battery_id, battery_data)
                    energy_gained = 20
                    
                    # Remove battery from grid and respawn it elsewhere
                    self.respawn_battery(battery_id)
            
            if energy_gained > 0:
                # Move to battery position and gain energy
                with self.shared_state.robots_mutex:
                    robot_data = self.shared_state.get_robot_data(self.id)
                    robot_data['x'] = new_x
                    robot_data['y'] = new_y
                    robot_data['E'] = min(ENERGY_LIMIT, robot_data['E'] + energy_gained - 1)  # -1 for movement
                    self.shared_state.set_robot_data(self.id, robot_data)
                
                # Update grid
                self.shared_state.set_grid_cell(old_x, old_y, EMPTY_SYMBOL)
                symbol = PLAYER_SYMBOL if self.is_player else str(self.id)
                self.shared_state.set_grid_cell(new_x, new_y, symbol)
    
    def initiate_duel(self, other_robot_id, old_x, old_y, new_x, new_y):
        """Initiate duel with another robot (grid_mutex already held)"""
        # Acquire robots_mutex to read/modify robot stats
        with self.shared_state.robots_mutex:
            my_data = self.shared_state.get_robot_data(self.id)
            other_data = self.shared_state.get_robot_data(other_robot_id)
            
            if not my_data or not other_data or my_data['status'] == 0 or other_data['status'] == 0:
                return  # One of the robots is already dead
            
            # Calculate power: Poder = 2*F + E
            my_power = 2 * my_data['F'] + my_data['E']
            other_power = 2 * other_data['F'] + other_data['E']
            
            print(f"DUEL! Robot {self.id} (power={my_power}) vs Robot {other_robot_id} (power={other_power})")
            
            if my_power > other_power:
                # I win - other robot dies
                other_data['status'] = 0
                self.shared_state.set_robot_data(other_robot_id, other_data)
                
                # Move to their position
                my_data['x'] = new_x
                my_data['y'] = new_y
                my_data['E'] = max(0, my_data['E'] - 1)  # Movement cost
                self.shared_state.set_robot_data(self.id, my_data)
                
                # Update grid
                self.shared_state.set_grid_cell(old_x, old_y, EMPTY_SYMBOL)
                symbol = PLAYER_SYMBOL if self.is_player else str(self.id)
                self.shared_state.set_grid_cell(new_x, new_y, symbol)
                
                print(f"Robot {self.id} wins! Robot {other_robot_id} is destroyed.")
                
            elif other_power > my_power:
                # I lose - I die
                my_data['status'] = 0
                self.shared_state.set_robot_data(self.id, my_data)
                self.shared_state.set_grid_cell(old_x, old_y, EMPTY_SYMBOL)
                
                print(f"Robot {other_robot_id} wins! Robot {self.id} is destroyed.")
                
            else:
                # Tie - both robots die
                my_data['status'] = 0
                other_data['status'] = 0
                self.shared_state.set_robot_data(self.id, my_data)
                self.shared_state.set_robot_data(other_robot_id, other_data)
                
                self.shared_state.set_grid_cell(old_x, old_y, EMPTY_SYMBOL)
                self.shared_state.set_grid_cell(new_x, new_y, EMPTY_SYMBOL)
                
                print(f"TIE! Both Robot {self.id} and Robot {other_robot_id} are destroyed.")
    
    def find_robot_at_position(self, x, y):
        """Find robot ID at given position"""
        for robot_id in range(MAX_ROBOTS):
            robot_data = self.shared_state.get_robot_data(robot_id)
            if robot_data and robot_data['status'] == 1 and robot_data['x'] == x and robot_data['y'] == y:
                return robot_id
        return None
    
    def find_battery_at_position(self, x, y):
        """Find battery ID at given position"""
        for battery_id in range(MAX_BATTERIES):
            battery_data = self.shared_state.get_battery_data(battery_id)
            if battery_data and battery_data['collected'] == 0 and battery_data['x'] == x and battery_data['y'] == y:
                return battery_id
        return None
    
    def respawn_battery(self, battery_id):
        """Respawn battery in a new location"""
        # Find empty position for battery respawn
        for attempt in range(100):  # Max attempts to avoid infinite loop
            new_x = random.randint(1, GRID_WIDTH-2)
            new_y = random.randint(1, GRID_HEIGHT-2)
            if self.shared_state.get_grid_cell(new_x, new_y) == EMPTY_SYMBOL:
                # Update battery data
                battery_data = {
                    'x': new_x, 'y': new_y, 'collected': 0, 'owner': -1
                }
                self.shared_state.set_battery_data(battery_id, battery_data)
                self.shared_state.set_grid_cell(new_x, new_y, BATTERY_SYMBOL)
                break
    
    def housekeeping(self):
        """Housekeeping thread - reduces energy when robot moves"""
        while self.running:
            try:
                time.sleep(1.0)  # Check every second
                
                with self.shared_state.robots_mutex:
                    robot_data = self.shared_state.get_robot_data(self.id)
                    if robot_data and robot_data['status'] == 1:
                        # Reduce energy based on robot stats
                        robot_data['E'] = max(0, robot_data['E'] - 0.5)
                        
                        # Check if robot dies
                        if robot_data['E'] <= 0:
                            robot_data['status'] = 0
                            
                            # Remove from grid
                            with self.shared_state.grid_mutex:
                                self.shared_state.set_grid_cell(robot_data['x'], robot_data['y'], EMPTY_SYMBOL)
                        
                        self.shared_state.set_robot_data(self.id, robot_data)
                        
                        if robot_data['status'] == 0:
                            print(f"Robot {self.id} died from energy depletion!")
                            break
                    else:
                        break  # Robot is dead
                        
            except Exception as e:
                print(f"Robot {self.id} housekeeping error: {e}")
                break
    
    def set_direction(self, dx, dy):
        """Set player robot direction"""
        if self.is_player and self.direction_queue:
            try:
                # Clear queue and add new direction
                while not self.direction_queue.empty():
                    self.direction_queue.get_nowait()
                self.direction_queue.put((dx, dy))
            except:
                pass
    
    def run(self):
        """Main robot process"""
        try:
            # Attach to shared memory
            self.attach_shared_memory()
            
            # Start housekeeping thread
            housekeeping_thread = threading.Thread(target=self.housekeeping, daemon=True)
            housekeeping_thread.start()
            
            # Wait for initialization to complete
            while True:
                flags = self.shared_state.get_flags()
                if flags['init_done']:
                    break
                time.sleep(0.1)
            
            # Main sense-act loop
            self.sense_act()
            
        except Exception as e:
            print(f"Robot {self.id} process error: {e}")
        finally:
            self.running = False

class Arena:
    """Main arena controller - handles initialization and coordinates game"""
    
    def __init__(self, num_robots=4, num_batteries=8):
        self.num_robots = min(num_robots, MAX_ROBOTS)
        self.num_batteries = min(num_batteries, MAX_BATTERIES)
        
        # Get shared locks
        self.shared_locks = get_shared_locks()
        
        # Create shared memory and initialize
        self.shared_state = SharedGameState(create=True, shared_locks=self.shared_locks)
        
        self.robot_processes = []
        self.batteries = []
        
        # Initialize game
        self._initialize_game()
    
    def _initialize_game(self):
        """Initialize game with proper synchronization"""
        
        # Acquire initialization lock to ensure only one process initializes
        with self.shared_state.init_mutex:
            flags = self.shared_state.get_flags()
            if flags['init_done']:
                return  # Already initialized
            
            print("Initializing robot arena...")
            
            # Create and place batteries
            self._place_batteries()
            
            # Create robot processes
            self._create_robots()
            
            # Mark initialization as complete
            flags['init_done'] = 1
            flags['alive_count'] = self.num_robots
            self.shared_state.set_flags(flags)
            
            print(f"Arena initialized with {self.num_robots} robots and {self.num_batteries} batteries")
    
    def _place_batteries(self):
        """Place batteries on the arena"""
        for battery_id in range(self.num_batteries):
            # Find empty position
            while True:
                x = random.randint(1, GRID_WIDTH-2)
                y = random.randint(1, GRID_HEIGHT-2)
                if self.shared_state.get_grid_cell(x, y) == EMPTY_SYMBOL:
                    break
            
            # Create battery and place on grid
            battery = Battery(x, y, battery_id, self.shared_state)
            self.batteries.append(battery)
            
            with self.shared_state.grid_mutex:
                self.shared_state.set_grid_cell(x, y, BATTERY_SYMBOL)
    
    def _create_robots(self):
        """Create robot processes"""
        # Create player robot (robot 0)
        player_x, player_y = GRID_WIDTH // 2, GRID_HEIGHT // 2
        player_robot = Robot(0, player_x, player_y, is_player=True, 
                           shared_memory_name='robot_arena_shm', shared_locks=self.shared_locks)
        
        # Initialize player robot in shared memory directly (don't attach shared_state to robot yet)
        with self.shared_state.robots_mutex:
            self.shared_state.set_robot_data(0, {
                'id': 0, 'x': player_x, 'y': player_y,
                'F': player_robot.F, 'E': player_robot.E, 'V': player_robot.V,
                'status': 1  # alive
            })
        
        with self.shared_state.grid_mutex:
            self.shared_state.set_grid_cell(player_x, player_y, PLAYER_SYMBOL)
        
        self.robot_processes.append(player_robot)
        
        # Create AI robots
        for robot_id in range(1, self.num_robots):
            # Find empty position
            while True:
                x = random.randint(1, GRID_WIDTH-2)
                y = random.randint(1, GRID_HEIGHT-2)
                if self.shared_state.get_grid_cell(x, y) == EMPTY_SYMBOL:
                    break
            
            robot = Robot(robot_id, x, y, is_player=False, 
                         shared_memory_name='robot_arena_shm', shared_locks=self.shared_locks)
            
            # Initialize robot in shared memory directly
            with self.shared_state.robots_mutex:
                self.shared_state.set_robot_data(robot_id, {
                    'id': robot_id, 'x': x, 'y': y,
                    'F': robot.F, 'E': robot.E, 'V': robot.V,
                    'status': 1  # alive
                })
            
            with self.shared_state.grid_mutex:
                self.shared_state.set_grid_cell(x, y, str(robot_id))
            
            self.robot_processes.append(robot)
    
    def start_robots(self):
        """Start all robot processes"""
        for robot_process in self.robot_processes:
            robot_process.start()
    
    def set_player_direction(self, dx, dy):
        """Set direction for player robot"""
        if self.robot_processes:
            self.robot_processes[0].set_direction(dx, dy)
    
    def update_alive_count(self):
        """Update count of alive robots"""
        alive_count = 0
        with self.shared_state.robots_mutex:
            for robot_id in range(self.num_robots):
                robot_data = self.shared_state.get_robot_data(robot_id)
                if robot_data and robot_data['status'] == 1:
                    alive_count += 1
        
        flags = self.shared_state.get_flags()
        flags['alive_count'] = alive_count
        
        # Check for game over
        if alive_count <= 1:
            flags['game_over'] = 1
            # Find winner
            for robot_id in range(self.num_robots):
                robot_data = self.shared_state.get_robot_data(robot_id)
                if robot_data and robot_data['status'] == 1:
                    flags['winner'] = robot_id
                    break
        
        self.shared_state.set_flags(flags)
        return alive_count
    
    def cleanup(self):
        """Clean up arena and processes"""
        print("Cleaning up arena...")
        
        # Stop all robot processes
        for robot_process in self.robot_processes:
            robot_process.running = False
            
        # Wait for processes to finish
        for robot_process in self.robot_processes:
            robot_process.join(timeout=2)
            if robot_process.is_alive():
                robot_process.terminate()
        
        # Clean up shared memory
        self.shared_state.cleanup()

class Viewer:
    """Passive viewer for displaying the game state"""
    
    def __init__(self, shared_state):
        self.shared_state = shared_state
        self.running = True
    
    def display_grid(self, stdscr):
        """Display the current game state"""
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()
        
        # Display grid
        for y in range(min(GRID_HEIGHT, max_y - 5)):
            row = ""
            for x in range(min(GRID_WIDTH, max_x - 1)):
                row += self.shared_state.get_grid_cell(x, y)
            stdscr.addstr(y, 0, row)
        
        # Display robot stats
        if GRID_HEIGHT + 1 < max_y:
            with self.shared_state.robots_mutex:
                player_data = self.shared_state.get_robot_data(0)
                if player_data:
                    status = "alive" if player_data['status'] == 1 else "dead"
                    energy_info = f"Player Robot: Energy={player_data['E']}, Force={player_data['F']}, Velocity={player_data['V']}, Status={status}"
                    stdscr.addstr(GRID_HEIGHT + 1, 0, energy_info[:max_x-1])
                other_robot_info = []
                for robot_id in range(1, MAX_ROBOTS):
                    # print robot stats
                    robot_data = self.shared_state.get_robot_data(robot_id)
                    if robot_data and robot_data['status'] == 1:
                        other_robot_info.append(f" Robot {robot_id}: E={robot_data['E']}, F={robot_data['F']}, V={robot_data['V']} ")
                if other_robot_info:
                    stdscr.addstr(GRID_HEIGHT + 2, 0, " | ".join(other_robot_info)[:max_x-1])
        
        # Display game status
        if GRID_HEIGHT + 2 < max_y:
            flags = self.shared_state.get_flags()
            status_info = f"Alive robots: {flags['alive_count']}"
            if flags['game_over']:
                if flags['winner'] >= 0:
                    status_info += f" | GAME OVER - Winner: Robot {flags['winner']}"
                else:
                    status_info += " | GAME OVER - No winner"
            stdscr.addstr(GRID_HEIGHT + 2, 0, status_info[:max_x-1])
        
        # Display controls
        if GRID_HEIGHT + 3 < max_y:
            controls = "Use arrow keys to move player robot. Q to quit."
            stdscr.addstr(GRID_HEIGHT + 3, 0, controls[:max_x-1])
        
        stdscr.refresh()
    
    def run(self, stdscr):
        """Main viewer loop"""
        stdscr.nodelay(True)
        
        while self.running:
            try:
                # Check for game over
                flags = self.shared_state.get_flags()
                if flags['game_over']:
                    self.display_grid(stdscr)
                    time.sleep(2)  # Show final state
                    break
                
                # Display current state
                self.display_grid(stdscr)
                
                # Check for input
                key = stdscr.getch()
                if key == ord('q'):
                    break
                
                # Small delay for smooth display
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Viewer error: {e}")
                break

def demonstrate_deadlock():
    """Demonstrate a deadlock scenario (for educational purposes)"""
    print("\n=== DEADLOCK DEMONSTRATION ===")
    print("This would create a deadlock if we didn't follow proper lock ordering:")
    print("Robot A: battery_mutex[0] -> grid_mutex")
    print("Robot B: grid_mutex -> battery_mutex[0]") 
    print("Solution: Always acquire locks in order: grid_mutex -> robots_mutex -> battery_mutexes")
    print("================================\n")

def main(stdscr):
    """Main game controller with viewer"""
    arena = None
    viewer = None
    
    try:
        # Show deadlock demonstration
        #demonstrate_deadlock()
        
        # Create and initialize arena
        print("Creating robot arena with shared memory...")
        arena = Arena(num_robots=5, num_batteries=8)
        
        # Start robot processes
        print("Starting robot processes...")
        arena.start_robots()
        
        # Create viewer attached to shared memory
        viewer = Viewer(arena.shared_state)
        
        # Main game loop with viewer
        print("Starting game... Use arrow keys to control player robot.")
        time.sleep(1)  # Give robots time to start
        
        # Enable non-blocking input so display updates in real-time
        stdscr.nodelay(True)
        
        while True:
            # Update alive count and check game state
            alive_count = arena.update_alive_count()
            
            # Display current state
            viewer.display_grid(stdscr)
            
            # Check for game over
            flags = arena.shared_state.get_flags()
            if flags['game_over']:
                # Show winner message
                if flags['winner'] >= 0:
                    winner_msg = f"GAME OVER! Winner: Robot {flags['winner']}"
                    if flags['winner'] == 0:
                        winner_msg += " (PLAYER WINS!)"
                else:
                    winner_msg = "GAME OVER! No winner (all robots destroyed)"
                
                stdscr.addstr(GRID_HEIGHT + 4, 0, winner_msg)
                stdscr.addstr(GRID_HEIGHT + 5, 0, "Press any key to exit...")
                stdscr.refresh()
                stdscr.nodelay(False)  # Switch back to blocking for final input
                stdscr.getch()  # Wait for key press
                break
            
            # Handle player input (non-blocking)
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
            # If key == -1, no key was pressed, which is fine - continue updating display
            
            # Update frequency control
            curses.napms(100)  # 100ms delay = ~10 FPS
            
    except KeyboardInterrupt:
        print("\nGame interrupted by user")
    except Exception as e:
        print(f"Game error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if arena:
            arena.cleanup()
        print("Game ended.")

def run_viewer_only():
    """Run standalone viewer (for testing)"""
    try:
        shared_locks = get_shared_locks()
        shared_state = SharedGameState(create=False, shared_locks=shared_locks)
        viewer = Viewer(shared_state)
        curses.wrapper(viewer.run)
    except Exception as e:
        print(f"Viewer error: {e}")

if __name__ == "__main__":
    # Set multiprocessing method for compatibility
    multiprocessing.set_start_method('spawn', force=True)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'viewer':
            run_viewer_only()
        else:
            print("Usage: python main.py [viewer]")
    else:
        # Run main game
        curses.wrapper(main)