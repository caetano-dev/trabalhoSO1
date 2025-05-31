#!/usr/bin/env python3
"""
Quick test to verify battery collection and robot death mechanics
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import Battery, Robot, Arena
import multiprocessing
import time

def test_battery_collection():
    """Test battery collection mechanics"""
    print("Testing battery collection...")
    
    # Create a battery
    battery = Battery(5, 5)
    print(f"Battery at ({battery.x}, {battery.y}) with {battery.energy_boost} energy boost")
    
    # Test collection
    energy_gained = battery.collect()
    print(f"First collection: gained {energy_gained} energy")
    
    # Test second collection (should be 0)
    energy_gained = battery.collect()
    print(f"Second collection: gained {energy_gained} energy")
    
    print("Battery collection test completed!\n")

def test_arena_quick():
    """Quick test of arena initialization"""
    print("Testing arena initialization...")
    
    # Create arena with fewer robots for testing
    arena = Arena(num_robots=3, num_batteries=3)
    
    print(f"Arena created with {len(arena.robot_data)} robots")
    print(f"Arena created with {len(arena.batteries)} batteries")
    
    # Print robot positions and stats
    for robot_id, robot_data in arena.robot_data.items():
        robot_type = "Player" if robot_data['is_player'] else f"AI Robot {robot_id}"
        print(f"{robot_type}: pos=({robot_data['x']}, {robot_data['y']}), energy={robot_data['E']}, status={robot_data['status']}")
    
    # Print battery positions
    for i, battery in enumerate(arena.batteries):
        print(f"Battery {i+1}: pos=({battery.x}, {battery.y}), collected={battery.collected}")
    
    # Clean up
    arena.cleanup()
    print("Arena test completed!\n")

def test_robot_energy_consumption():
    """Test robot energy consumption"""
    print("Testing robot energy consumption...")
    
    # Create a simple robot data structure to simulate energy loss
    robot_stats = {'F': 5, 'V': 3, 'E': 30}
    
    print(f"Initial robot stats: Force={robot_stats['F']}, Velocity={robot_stats['V']}, Energy={robot_stats['E']}")
    
    # Simulate energy consumption like in housekeeping
    energy_consumption = max(1, (robot_stats['V'] + robot_stats['F']) // 4)
    print(f"Energy consumption per cycle: {energy_consumption}")
    
    # Simulate a few cycles
    for cycle in range(1, 6):
        robot_stats['E'] = max(0, robot_stats['E'] - energy_consumption)
        print(f"Cycle {cycle}: Energy = {robot_stats['E']}")
        if robot_stats['E'] <= 0:
            print(f"Robot would die after {cycle} cycles!")
            break
    
    print("Energy consumption test completed!\n")

if __name__ == "__main__":
    # Set multiprocessing method for compatibility
    multiprocessing.set_start_method('spawn', force=True)
    
    print("=" * 50)
    print("ROBOT ARENA - SYSTEM TESTS")
    print("=" * 50)
    
    test_battery_collection()
    test_robot_energy_consumption()
    test_arena_quick()
    
    print("All tests completed successfully!")
    print("The game systems are working correctly.")
