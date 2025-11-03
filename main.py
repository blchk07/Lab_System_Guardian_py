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
PLAYER_HP, PLAYER_SPEED, SHOOT_COOLDOWN = 100, 0.08, 0.22
BULLET_SPEED, PLAYER_DAMAGE = 0.8, 30
WALL_COST, WALL_HP = 40, 100

ENEMY_SPAWN_DISTANCE = 25
MONEY_PER_KILL, STARTING_MONEY = 30, 50
FRAME_DELAY = 0.04
SAVE_FILE_JSON = "game_save.json"

COLOR_RESET, COLOR_RED, COLOR_GREEN, COLOR_MAGENTA, COLOR_CYAN, COLOR_GRAY, COLOR_YELLOW, COLOR_BLUE = '\033[0m', '\033[91m', '\033[92m', '\033[95m', '\033[96m', '\033[90m', '\033[93m', '\033[94m'
SYMBOL_EMPTY, SYMBOL_PLAYER, SYMBOL_CORE, SYMBOL_WALL, SYMBOL_PLAYER_WALL, SYMBOL_BULLET, SYMBOL_ENEMY_BASIC = ' ', f'{COLOR_CYAN}@{COLOR_RESET}', f'{COLOR_MAGENTA}◈{COLOR_RESET}', f'{COLOR_GRAY}█{COLOR_RESET}', f'{COLOR_BLUE}▓{COLOR_RESET}', f'{COLOR_YELLOW}•{COLOR_RESET}', f'{COLOR_RED}Ω{COLOR_RESET}'

ENEMY_TYPES = {
    'basic': {'hp': 30, 'hp_w': 5, 'dmg': 10, 'dmg_w': 2, 'speed': 0.45, 'symbol': SYMBOL_ENEMY_BASIC}
}

distance_sq = lambda p1, p2: (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2
distance = lambda p1, p2: math.hypot(p1[0] - p2[0], p1[1] - p2[1])

class GameObject:
    def __init__(self, x, y, symbol):
        self.x, self.y, self.symbol, self.active = x, y, symbol, True

class Core(GameObject):
    def __init__(self, x, y):
        super().__init__(x, y, SYMBOL_CORE)
        self.hp, self.max_hp = CORE_HP, CORE_HP
    def take_damage(self, damage): self.hp = max(0, self.hp - damage)
    @property
    def is_dead(self): return self.hp <= 0

class Player(GameObject):
    def __init__(self, x, y):
        super().__init__(x, y, SYMBOL_PLAYER)
        self.hp, self.max_hp = PLAYER_HP, PLAYER_HP
        self.last_dir_x, self.last_dir_y = 0, -1
        self.last_move_time, self.last_shoot_time = 0, 0
        self._money, self.kills = STARTING_MONEY, 0

    def move(self, dx, dy, /, game_map, enemies):
        if time.time() - self.last_move_time < PLAYER_SPEED: return False
        new_x, new_y = self.x + dx, self.y + dy
        if not (0 < new_x < MAP_WIDTH - 1 and 0 < new_y < MAP_HEIGHT - 1) or \
           game_map[new_y][new_x] == 'wall' or any(e.x == new_x and e.y == new_y for e in enemies):
            return False
        self.x, self.y = new_x, new_y
        self.last_move_time = time.time()
        if dx != 0 or dy != 0: self.last_dir_x, self.last_dir_y = dx, dy
        return True

    def shoot(self):
        if time.time() - self.last_shoot_time < SHOOT_COOLDOWN: return None
        self.last_shoot_time = time.time()
        return Bullet(self.x, self.y, self.last_dir_x, self.last_dir_y, PLAYER_DAMAGE, True)

    def take_damage(self, damage): self.hp = max(0, self.hp - damage)
    def spend_money(self, amount):
        if self._money >= amount: self._money -= amount; return True
        return False
    
    @property
    def is_dead(self): return self.hp <= 0

class Bullet(GameObject):
    def __init__(self, x, y, dx, dy, damage, is_player_bullet):
        super().__init__(x, y, SYMBOL_BULLET)
        self.dx, self.dy, self.damage, self.is_player_bullet = dx, dy, damage, is_player_bullet
    
    def update(self, game_map):
        self.x += self.dx * BULLET_SPEED
        self.y += self.dy * BULLET_SPEED
        new_x, new_y = self.get_grid_pos()

        if not (0 < self.x < MAP_WIDTH - 1 and 0 < self.y < MAP_HEIGHT - 1) or game_map[new_y][new_x] == 'wall':
            self.active = False
            return False
        return True

    def get_grid_pos(self): return int(round(self.x)), int(round(self.y))

class Wall(GameObject):
    def __init__(self, x, y):
        super().__init__(x, y, SYMBOL_PLAYER_WALL)
        self.hp, self.max_hp = WALL_HP, WALL_HP
    def take_damage(self, damage):
        self.hp = max(0, self.hp - damage)
        if self.hp <= 0: self.active = False
        return not self.active

class Enemy(GameObject):
    def __init__(self, x, y, wave, type_key):
        stats = ENEMY_TYPES[type_key]
        super().__init__(x, y, stats['symbol'])
        self.hp = stats['hp'] + wave * stats['hp_w']
        self.damage = stats['dmg'] + wave * stats['dmg_w']
        self.speed = stats['speed']
        self.last_move_time, self.last_attack_time = 0, 0
        self.attack_cooldown = 1.0

    @property
    def is_dead(self): return self.hp <= 0
    def take_damage(self, damage): self.hp = max(0, self.hp - damage)
    def is_adjacent_to(self, target_x, target_y): return abs(self.x - target_x) + abs(self.y - target_y) <= 1

    def move_towards(self, target_x, target_y, game):
        if time.time() - self.last_move_time < self.speed: return
        self.last_move_time = time.time()

        dx = target_x - self.x
        dy = target_y - self.y
        step_x = (1 if dx > 0 else -1) if dx != 0 else 0
        step_y = (1 if dy > 0 else -1) if dy != 0 else 0
        
        primary_move, secondary_move = ((step_x, 0), (0, step_y)) if abs(dx) > abs(dy) else ((0, step_y), (step_x, 0))

        if self._try_move_to(self.x + primary_move[0], self.y + primary_move[1], game): return
        if self._try_move_to(self.x + secondary_move[0], self.y + secondary_move[1], game): return

    def _try_move_to(self, nx, ny, game):
        if not (0 < nx < MAP_WIDTH - 1 and 0 < ny < MAP_HEIGHT - 1) or game.map[ny][nx] == 'wall' or \
           (nx, ny) == (game.player.x, game.player.y) or (nx, ny) == (game.core.x, game.core.y) or \
           any(e.x == nx and e.y == ny for e in game.enemies if e is not self):
            return False
        self.x, self.y = nx, ny
        return True

    def attack_target(self, target):
        if time.time() - self.last_attack_time > self.attack_cooldown:
            self.last_attack_time = time.time()
            target.take_damage(self.damage)

class Game:
    def __init__(self):
        self.running = True
        self.wave = 0
        self.wave_in_progress = False
        self.inter_wave_pause = False
        self.game_outcome = ""
        self.map = self._create_map()
        self.core = Core(CORE_X, CORE_Y)
        self.player = Player(CORE_X + 3, CORE_Y + 3)
        self.enemies, self.bullets, self.walls = [], [], []
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

    def spawn_wave(self):
        self.wave += 1
        self.wave_in_progress = True
        self.enemies.clear()
        
        num_enemies = 4 + self.wave * 2
        
        for _ in range(num_enemies):
            for _ in range(50):
                side = random.randint(0, 3)
                if side < 2: x, y = random.randint(5, MAP_WIDTH - 5), 2 if side == 0 else MAP_HEIGHT - 3
                else: x, y = 2 if side == 2 else MAP_WIDTH - 3, random.randint(5, MAP_HEIGHT - 5)
                if distance((x, y), (self.player.x, self.player.y)) > ENEMY_SPAWN_DISTANCE: break
            else: continue
            
            self.enemies.append(Enemy(x, y, self.wave, 'basic'))
    
    def _update_bullets(self):
        bullets_to_keep = []
        for bullet in self.bullets:
            if not bullet.update(self.map): continue

            bx, by = bullet.get_grid_pos()
            hit_target = False
            
            if bullet.is_player_bullet:
                for enemy in self.enemies:
                    if not enemy.is_dead and (enemy.x, enemy.y) == (bx, by):
                        enemy.take_damage(bullet.damage)
                        hit_target = True
                        if enemy.is_dead: self.player._money += MONEY_PER_KILL; self.player.kills += 1
                        break
            else:
                if (self.player.x, self.player.y) == (bx, by): self.player.take_damage(bullet.damage); hit_target = True
                elif (self.core.x, self.core.y) == (bx, by): self.core.take_damage(bullet.damage); hit_target = True
            
            if hit_target: continue

            if self.map[by][bx] == 'wall' and not bullet.is_player_bullet:
                for wall in self.walls:
                    if (wall.x, wall.y) == (bx, by):
                        wall.take_damage(bullet.damage)
                        break
                continue
                
            bullets_to_keep.append(bullet)
        self.bullets = bullets_to_keep

    def _update_enemies(self):
        self.enemies = [e for e in self.enemies if not e.is_dead]
        for enemy in self.enemies:
            dist_to_core_sq = distance_sq((enemy.x, enemy.y), (self.core.x, self.core.y))
            dist_to_player_sq = distance_sq((enemy.x, enemy.y), (self.player.x, self.player.y))
            target = self.core if dist_to_core_sq < dist_to_player_sq else self.player
            
            enemy.move_towards(target.x, target.y, self)
            
            if enemy.is_adjacent_to(target.x, target.y): enemy.attack_target(target)

    def _update_walls(self):
        active_walls = []
        for wall in self.walls:
            if wall.active:
                active_walls.append(wall)
            else:
                self.map[wall.y][wall.x] = 'empty'
        self.walls = active_walls

    def update(self):
        if self.inter_wave_pause: return
        if not self.wave_in_progress and not self.enemies:
            self.inter_wave_pause = True; return
            
        self._update_bullets()
        self._update_enemies()
        self._update_walls()

        if not self.enemies and self.wave_in_progress:
            self.wave_in_progress = False
            self.inter_wave_pause = True
        
        if self.player.is_dead or self.core.is_dead:
            self.running = False
    
    def _handle_game_input(self, key):
        moves = {'w': (0, -1), 's': (0, 1), 'a': (-1, 0), 'd': (1, 0)}
        if key in moves: self.player.move(*moves[key], game_map=self.map, enemies=self.enemies)
        elif key == 'b':
            if (bullet := self.player.shoot()): self.bullets.append(bullet)
        elif key == 'e': self.build_wall()
        elif key == 'q': self.running = False; self.game_outcome = "exit"

    def _handle_inter_wave_input(self, key):
        if key == 'c': self.inter_wave_pause = False; self.spawn_wave()
        elif key == 'q': self.running = False; self.game_outcome = "exit"

    def handle_input(self):
        if msvcrt.kbhit():
            try:
                ch = msvcrt.getch()
                if ch in [b'\x00', b'\xe0']: msvcrt.getch(); return
                key = ch.decode('utf-8').lower()
                if self.inter_wave_pause: self._handle_inter_wave_input(key)
                elif self.wave_in_progress: self._handle_game_input(key)
            except (UnicodeDecodeError, KeyError): pass
    
    def build_wall(self):
        wx, wy = self.player.x + self.player.last_dir_x, self.player.y + self.player.last_dir_y
        if not (0 < wx < MAP_WIDTH - 1 and 0 < wy < MAP_HEIGHT - 1) or self.map[wy][wx] == 'wall' or \
           (wx, wy) == (self.core.x, self.core.y) or \
           any(e.x == wx and e.y == wy for e in self.enemies):
            return
        if self.player.spend_money(WALL_COST):
            self.walls.append(Wall(wx, wy))
            self.map[wy][wx] = 'wall'
    
    def render(self): 
        cam_x = max(0, min(self.player.x - CAMERA_WIDTH // 2, MAP_WIDTH - CAMERA_WIDTH))
        cam_y = max(0, min(self.player.y - CAMERA_HEIGHT // 2, MAP_HEIGHT - CAMERA_HEIGHT))

        lines = []
        for y in range(CAMERA_HEIGHT):
            row = []
            for x in range(CAMERA_WIDTH):
                map_x, map_y = cam_x + x, cam_y + y
                coords = (map_x, map_y)
                cell = SYMBOL_EMPTY

                if any(w.x == map_x and w.y == map_y for w in self.walls): cell = SYMBOL_PLAYER_WALL
                elif self.map[map_y][map_x] == 'wall': cell = SYMBOL_WALL
                
                dynamic_symbol = None
                for obj in self.enemies + self.bullets:
                    obj_coords = obj.get_grid_pos() if isinstance(obj, Bullet) else (obj.x, obj.y)
                    if obj_coords == coords:
                        dynamic_symbol = obj.symbol
                        break
                
                if dynamic_symbol: cell = dynamic_symbol
                
                if coords == (self.core.x, self.core.y): cell = SYMBOL_CORE
                elif coords == (self.player.x, self.player.y): cell = SYMBOL_PLAYER
                
                row.append(cell)
            lines.append(''.join(row))
            
        frame_content = '\n'.join(lines) + '\n' + f'{COLOR_CYAN}{"="*CAMERA_WIDTH}{COLOR_RESET}\n'
        frame_content += f'{COLOR_GREEN}HP: {self.player.hp}{COLOR_RESET} | {COLOR_MAGENTA}Core: {self.core.hp}{COLOR_RESET} | {COLOR_YELLOW}Money: ${self.player._money}{COLOR_RESET} | {COLOR_RED}Wave: {self.wave}{COLOR_RESET} | Enemies: {len(self.enemies)}\n'
        
        if self.inter_wave_pause:
            frame_content += f'{COLOR_YELLOW}WAVE {self.wave} CLEARED!{COLOR_RESET} (C)ontinue | {COLOR_RED}Q{COLOR_RESET}-Quit\n'
        else:
            frame_content += f'{COLOR_BLUE}WASD{COLOR_RESET}-Move | {COLOR_YELLOW}B{COLOR_RESET}-Shoot | {COLOR_GREEN}E{COLOR_RESET}-Wall(${WALL_COST}) | {COLOR_RED}Q{COLOR_RESET}-Quit\n'
        
        if frame_content != self.last_frame:
            sys.stdout.write('\033[H' + frame_content)
            sys.stdout.flush()
            self.last_frame = frame_content
    
    def run(self):
        try:
            print('\033[?25l\033[2J', end='', flush=True) 
            if self.wave == 0 and not self.inter_wave_pause: self.spawn_wave()
            while self.running:
                self.handle_input()
                self.update()
                self.render()
                time.sleep(FRAME_DELAY)
            return self.game_outcome
        finally:
            print('\033[?25h', end='', flush=True)
            os.system('cls' if os.name == 'nt' else 'clear')

def main():
    game = Game()
    game.run()

if __name__ == '__main__':
    main()