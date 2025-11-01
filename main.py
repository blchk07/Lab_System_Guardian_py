import os
import sys
import time
import random
import math
import msvcrt
import json

MAP_WIDTH, MAP_HEIGHT = 80, 50
CAMERA_WIDTH, CAMERA_HEIGHT = 40, 20

CORE_X, CORE_Y, CORE_HP = 5, 5, 150
PLAYER_HP, PLAYER_SPEED = 100, 0.08
FRAME_DELAY = 0.04

COLOR_RESET, COLOR_RED, COLOR_MAGENTA, COLOR_CYAN, COLOR_GRAY = '\033[0m', '\033[91m', '\033[95m', '\033[96m', '\033[90m'
SYMBOL_EMPTY, SYMBOL_PLAYER, SYMBOL_CORE, SYMBOL_WALL = ' ', f'{COLOR_CYAN}@{COLOR_RESET}', f'{COLOR_MAGENTA}◈{COLOR_RESET}', f'{COLOR_GRAY}█{COLOR_RESET}'

distance = lambda p1, p2: math.hypot(p1[0] - p2[0], p1[1] - p2[1])

class GameObject:
    def __init__(self, x, y, symbol):
        self.x, self.y, self.symbol, self.active = x, y, symbol, True

class Core(GameObject):
    def __init__(self, x, y):
        super().__init__(x, y, SYMBOL_CORE)
        self.hp, self.max_hp = CORE_HP, CORE_HP

class Player(GameObject):
    def __init__(self, x, y):
        super().__init__(x, y, SYMBOL_PLAYER)
        self.hp, self.max_hp = PLAYER_HP, PLAYER_HP
        self.last_move_time = 0

    def move(self, dx, dy, /, game_map):
        if time.time() - self.last_move_time < PLAYER_SPEED: return False
        new_x, new_y = self.x + dx, self.y + dy
        if not (0 < new_x < MAP_WIDTH - 1 and 0 < new_y < MAP_HEIGHT - 1) or \
           game_map[new_y][new_x] == 'wall':
            return False
        self.x, self.y = new_x, new_y
        self.last_move_time = time.time()
        return True

class Game:
    def __init__(self):
        self.running = True
        self.map = self._create_map()
        self.core = Core(CORE_X, CORE_Y)
        self.player = Player(CORE_X + 3, CORE_Y + 3)
        self.last_frame = ""
        os.system('')

    def _create_map(self):
        game_map = [['empty' for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                if y in (0, MAP_HEIGHT - 1) or x in (0, MAP_WIDTH - 1): game_map[y][x] = 'wall'
        for _ in range(35):
            x, y = random.randint(1, MAP_WIDTH - 2), random.randint(1, MAP_HEIGHT - 2)
            if distance((x, y), (CORE_X, CORE_Y)) > 4: game_map[y][x] = 'wall'
        return game_map

    def update(self):
        pass

    def _handle_game_input(self, key):
        moves = {'w': (0, -1), 's': (0, 1), 'a': (-1, 0), 'd': (1, 0)}
        if key in moves: self.player.move(*moves[key], game_map=self.map)
        elif key == 'q': self.running = False

    def handle_input(self):
        if msvcrt.kbhit():
            try:
                ch = msvcrt.getch()
                if ch in [b'\x00', b'\xe0']: msvcrt.getch(); return
                key = ch.decode('utf-8').lower()
                self._handle_game_input(key)
            except (UnicodeDecodeError, KeyError): pass

    def render(self): 
        cam_x = max(0, min(self.player.x - CAMERA_WIDTH // 2, MAP_WIDTH - CAMERA_WIDTH))
        cam_y = max(0, min(self.player.y - CAMERA_HEIGHT // 2, MAP_HEIGHT - CAMERA_HEIGHT))
        
        lines = []
        for y in range(CAMERA_HEIGHT):
            row = []
            for x in range(CAMERA_WIDTH):
                map_x, map_y = cam_x + x, cam_y + y
                cell = SYMBOL_EMPTY

                if self.map[map_y][map_x] == 'wall': cell = SYMBOL_WALL
                if (map_x, map_y) == (self.core.x, self.core.y): cell = SYMBOL_CORE
                elif (map_x, map_y) == (self.player.x, self.player.y): cell = SYMBOL_PLAYER
                
                row.append(cell)
            lines.append(''.join(row))
            
        frame_content = '\n'.join(lines) + '\n' + f'{COLOR_CYAN}{"="*CAMERA_WIDTH}{COLOR_RESET}\n'
        frame_content += f'{COLOR_CYAN}Q{COLOR_RESET}-Quit\n'
        
        if frame_content != self.last_frame:
            sys.stdout.write('\033[H' + frame_content)
            sys.stdout.flush()
            self.last_frame = frame_content
    
    def run(self):
        try:
            print('\033[?25l\033[2J', end='', flush=True) 
            while self.running:
                self.handle_input()
                self.update()
                self.render()
                time.sleep(FRAME_DELAY)
        finally:
            print('\033[?25h', end='', flush=True)
            os.system('cls' if os.name == 'nt' else 'clear')

def main():
    game = Game()
    game.run()

if __name__ == '__main__':
    main()