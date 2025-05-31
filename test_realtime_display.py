#!/usr/bin/env python3
"""
Test script to verify that the curses display updates in real-time
even when the player doesn't provide input.
"""

import curses
import multiprocessing
import time
from main import Arena, Viewer

def test_realtime_display(stdscr):
    """Test that the display updates continuously without player input"""
    
    # Set multiprocessing method
    multiprocessing.set_start_method('spawn', force=True)
    
    # Show instructions
    stdscr.addstr(0, 0, "Testing real-time display updates...")
    stdscr.addstr(1, 0, "The arena should update automatically showing AI robot movements.")
    stdscr.addstr(2, 0, "You should NOT need to press any keys to see updates.")
    stdscr.addstr(3, 0, "Press 'q' to quit when you're satisfied with the test.")
    stdscr.addstr(4, 0, "Starting in 3 seconds...")
    stdscr.refresh()
    time.sleep(3)
    
    # Create arena with AI robots
    arena = Arena(num_robots=4, num_batteries=6)
    arena.start_robots()
    
    # Create viewer
    viewer = Viewer(arena.shared_state)
    
    # Enable non-blocking input
    stdscr.nodelay(True)
    
    try:
        # Main display loop
        start_time = time.time()
        while True:
            # Update display every frame
            viewer.display_grid(stdscr)
            
            # Show test info
            elapsed = int(time.time() - start_time)
            stdscr.addstr(0, 0, f"Real-time display test - Running for {elapsed}s")
            stdscr.addstr(1, 0, "Watch AI robots move automatically without pressing keys!")
            stdscr.addstr(2, 0, "Press 'q' to quit")
            
            # Check for quit command (non-blocking)
            key = stdscr.getch()
            if key == ord('q'):
                break
            
            # Check for game over
            flags = arena.shared_state.get_flags()
            if flags['game_over']:
                stdscr.addstr(3, 0, "Game Over! Press 'q' to quit")
                stdscr.refresh()
            
            # Update at ~10 FPS
            time.sleep(0.1)
            
    finally:
        arena.cleanup()
        stdscr.addstr(25, 0, "Test completed! The display should have updated automatically.")
        stdscr.addstr(26, 0, "Press any key to exit...")
        stdscr.nodelay(False)
        stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(test_realtime_display)
