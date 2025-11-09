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
WALL_ATTACK_RADIUS = 4.0
MONEY_PER_KILL, STARTING_MONEY = 30, 50
FRAME_DELAY = 0.04
SAVE_FILE_JSON = "game_save.json"


COLOR_RESET, COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, COLOR_GRAY, COLOR_ORANGE = '\033[0m', '\033[91m', '\033[92m', '\033[93m', '\033[94m', '\033[95m', '\033[96m', '\033[90m', '\033[38;5;208m'
SYMBOL_EMPTY, SYMBOL_PLAYER, SYMBOL_CORE, SYMBOL_WALL, SYMBOL_PLAYER_WALL, SYMBOL_BULLET, SYMBOL_ENEMY_BULLET, SYMBOL_ENEMY_BASIC, SYMBOL_ENEMY_FAST, SYMBOL_ENEMY_TANK, SYMBOL_ENEMY_SHOOTER = ' ', f'{COLOR_CYAN}@{COLOR_RESET}', f'{COLOR_MAGENTA}◈{COLOR_RESET}', f'{COLOR_GRAY}█{COLOR_RESET}', f'{COLOR_BLUE}▓{COLOR_RESET}', f'{COLOR_YELLOW}•{COLOR_RESET}', f'{COLOR_RED}●{COLOR_RESET}', f'{COLOR_RED}Ω{COLOR_RESET}', f'{COLOR_ORANGE}δ{COLOR_RESET}', f'{COLOR_RED}Φ{COLOR_RESET}', f'{COLOR_RED}Ψ{COLOR_RESET}'

ENEMY_TYPES = {
    'basic': {'hp': 30, 'hp_w': 5, 'dmg': 10, 'dmg_w': 2, 'speed': 0.45, 'symbol': SYMBOL_ENEMY_BASIC},
    'fast': {'hp': 20, 'hp_w': 3, 'dmg': 5, 'dmg_w': 1, 'speed': 0.25, 'symbol': SYMBOL_ENEMY_FAST},
    'tank': {'hp': 60, 'hp_w': 10, 'dmg': 15, 'dmg_w': 3, 'speed': 0.65, 'symbol': SYMBOL_ENEMY_TANK},
    'shooter': {'hp': 25, 'hp_w': 4, 'dmg': 8, 'dmg_w': 2, 'speed': 0.55, 'symbol': SYMBOL_ENEMY_SHOOTER, 'range': 15}
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

    @property
    def money(self): return self._money
    @money.setter
    def money(self, value): self._money = max(0, value)
    @property
    def is_dead(self): return self.hp <= 0

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
        if self.money >= amount: self.money -= amount; return True
        return False

class Bullet(GameObject):
    def __init__(self, x, y, dx, dy, damage, is_player_bullet):
        super().__init__(x, y, SYMBOL_BULLET if is_player_bullet else SYMBOL_ENEMY_BULLET)
        self.dx, self.dy, self.damage, self.is_player_bullet = dx, dy, damage, is_player_bullet
    
    def update(self, game_map):
        prev_x, prev_y = self.get_grid_pos()
        self.x += self.dx * BULLET_SPEED
        self.y += self.dy * BULLET_SPEED
        new_x, new_y = self.get_grid_pos()

        if not (0 < self.x < MAP_WIDTH - 1 and 0 < self.y < MAP_HEIGHT - 1):
            self.active = False
            return False

        if prev_x != new_x and prev_y != new_y:
            if game_map[prev_y][new_x] == 'wall' and game_map[new_y][prev_x] == 'wall':
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

class Shooting: 
    def try_shoot(self, target_x, target_y):
        if time.time() - self.last_shoot_time < self.shoot_cooldown: return None
        dx, dy = target_x - self.x, target_y - self.y
        dist = distance((self.x, self.y), (target_x, target_y))
        if 0 < dist <= self.shoot_range:
            self.last_shoot_time = time.time()
            return Bullet(self.x, self.y, dx / dist, dy / dist, self.damage, False)
        return None

class Enemy(GameObject):
    def __init__(self, x, y, wave, type_key):
        stats = ENEMY_TYPES[type_key]
        super().__init__(x, y, stats['symbol'])
        self.hp = stats['hp'] + wave * stats['hp_w']
        self.damage = stats['dmg'] + wave * stats['dmg_w']
        self.speed = stats['speed']
        self.last_move_time, self.last_attack_time = 0, 0
        self.attack_cooldown, self.wall_attack_cooldown = 1.0, 0.8
        self.last_wall_attack_time = 0
        self.is_melee = 'range' not in stats

    @property
    def is_dead(self): return self.hp <= 0
    def take_damage(self, damage): self.hp = max(0, self.hp - damage)
    def is_adjacent_to(self, target_x, target_y): return abs(self.x - target_x) + abs(self.y - target_y) == 1

    def move_towards(self, target_x, target_y, game):
        if time.time() - self.last_move_time < self.speed:
            return
        self.last_move_time = time.time()

        dx = target_x - self.x
        dy = target_y - self.y
        step_x = (1 if dx > 0 else -1) if dx != 0 else 0
        step_y = (1 if dy > 0 else -1) if dy != 0 else 0
        
        primary_move, secondary_move = ((step_x, 0), (0, step_y)) if abs(dx) > abs(dy) else ((0, step_y), (step_x, 0))

        if self._try_move_to(self.x + primary_move[0], self.y + primary_move[1], game):
            return

        if self._try_move_to(self.x + secondary_move[0], self.y + secondary_move[1], game):
            return

    def _try_move_to(self, nx, ny, game):
        if self._can_stand(nx, ny, game):
            self.x, self.y = nx, ny
            return True

        if game.map[ny][nx] == 'wall':
            is_player_wall = False
            wall = None
            for w in game.walls:
                if w.x == nx and w.y == ny and w.active:
                    is_player_wall = True
                    wall = w
                    break
            
            if is_player_wall and distance((nx, ny), (game.core.x, game.core.y)) <= WALL_ATTACK_RADIUS:
                if time.time() - self.last_wall_attack_time > self.wall_attack_cooldown:
                    self.last_wall_attack_time = time.time()
                    if wall.take_damage(self.damage) and self.is_melee:
                        self.hp = 0
                return False
        return False

    def _can_stand(self, x, y, game):
        if not (0 < x < MAP_WIDTH - 1 and 0 < y < MAP_HEIGHT - 1):
            return False
        if game.map[y][x] == 'wall':
            return False
        if (x, y) == (game.player.x, game.player.y) or (x, y) == (game.core.x, game.core.y):
            return False
        if any(e.x == x and e.y == y for e in game.enemies if e is not self):
            return False
        return True

    def attack_target(self, target):
        if time.time() - self.last_attack_time > self.attack_cooldown:
            self.last_attack_time = time.time()
            target.take_damage(self.damage)

class EnemyShooter(Shooting, Enemy): 
    def __init__(self, x, y, wave, type_key='shooter'):
        Enemy.__init__(self, x, y, wave, type_key)
        stats = ENEMY_TYPES[type_key]
        self.shoot_range = stats.get('range', 0)
        self.shoot_cooldown = 2.5
        self.last_shoot_time = 0

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
        self.encountered_enemy_types = set()
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

    def save_game(self):
        p_data = {k: v for k, v in self.player.__dict__.items() if not k.startswith('last_')}
        c_data = {'x': self.core.x, 'y': self.core.y, 'hp': self.core.hp, 'max_hp': self.core.max_hp}
        w_data = [{'x': w.x, 'y': w.y, 'hp': w.hp} for w in self.walls if w.active]
        state = {'player': p_data, 'core': c_data, 'wave': self.wave, 'walls': w_data}
        try:
            with open(SAVE_FILE_JSON, 'w', encoding='utf-8') as f: json.dump(state, f, indent=2)
            return True
        except IOError: return False

    def load_game(self):
        if not os.path.exists(SAVE_FILE_JSON): return False
        try:
            with open(SAVE_FILE_JSON, 'r', encoding='utf-8') as f: data = json.load(f)
            self.player.__dict__.update(data['player'])
            self.core.__dict__.update(data['core'])
            self.wave = data['wave']
            self.walls.clear()
            for wall_data in data.get('walls', []):
                wall = Wall(wall_data['x'], wall_data['y'])
                wall.hp = wall_data['hp']
                self.walls.append(wall)
                self.map[wall.y][wall.x] = 'wall'
            self.player.x, self.player.y = self._find_safe_spawn_point()
            self.inter_wave_pause = True
            return True
        except (IOError, json.JSONDecodeError): return False
            
    def _find_safe_spawn_point(self):
        for r in range(1, 10):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if abs(dx) + abs(dy) != r: continue
                    x, y = self.core.x + dx, self.core.y + dy
                    if 0 < x < MAP_WIDTH - 1 and 0 < y < MAP_HEIGHT - 1 and self.map[y][x] != 'wall':
                        return x, y
        return self.core.x + 3, self.core.y + 3

    def spawn_wave(self):
        self.wave += 1
        self.wave_in_progress = True
        self.enemies.clear()
        self.player.x, self.player.y = self._find_safe_spawn_point()
        
        num_enemies = 4 + self.wave * 2
        enemy_chances = {'basic': 50, 'fast': 30, 'tank': 20}
        if self.wave >= 3: enemy_chances['shooter'] = 15
        
        enemy_types_to_spawn = random.choices(list(enemy_chances.keys()), weights=list(enemy_chances.values()), k=num_enemies)
        
        for enemy_type in enemy_types_to_spawn:
            for _ in range(50):
                side = random.randint(0, 3)
                if side < 2: x, y = random.randint(5, MAP_WIDTH - 5), 2 if side == 0 else MAP_HEIGHT - 3
                else: x, y = 2 if side == 2 else MAP_WIDTH - 3, random.randint(5, MAP_HEIGHT - 5)
                if distance((x, y), (self.player.x, self.player.y)) > ENEMY_SPAWN_DISTANCE: break
            else: continue
            
            self.encountered_enemy_types.add(enemy_type)
            if enemy_type == 'shooter': self.enemies.append(EnemyShooter(x, y, self.wave))
            else: self.enemies.append(Enemy(x, y, self.wave, enemy_type))
    
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
                        if enemy.is_dead: self.player.money += MONEY_PER_KILL; self.player.kills += 1
                        break
            else:
                if (self.player.x, self.player.y) == (bx, by): self.player.take_damage(bullet.damage); hit_target = True
                elif (self.core.x, self.core.y) == (bx, by): self.core.take_damage(bullet.damage); hit_target = True
            
            if hit_target: continue

            if self.map[by][bx] == 'wall':
                if not bullet.is_player_bullet:
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
            
            if isinstance(enemy, Shooting):
                if (bullet := enemy.try_shoot(target.x, target.y)): self.bullets.append(bullet)
            
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
        elif key == 's': self.save_game(); self.inter_wave_pause = False; self.spawn_wave()
        elif key == 'x': self.save_game(); self.running = False; self.game_outcome = "exit"

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

        player_walls_coords = {(w.x, w.y) for w in self.walls}
        dynamic_objects = {obj.get_grid_pos() if isinstance(obj, Bullet) else (obj.x, obj.y): obj.symbol for obj in self.enemies + self.bullets}

        lines = []
        for y in range(CAMERA_HEIGHT):
            row = []
            for x in range(CAMERA_WIDTH):
                map_x, map_y = cam_x + x, cam_y + y
                coords = (map_x, map_y)
                cell = SYMBOL_EMPTY

                if coords in player_walls_coords: cell = SYMBOL_PLAYER_WALL
                elif self.map[map_y][map_x] == 'wall': cell = SYMBOL_WALL
                
                if coords in dynamic_objects: cell = dynamic_objects[coords]
                
                if coords == (self.core.x, self.core.y): cell = SYMBOL_CORE
                elif coords == (self.player.x, self.player.y): cell = SYMBOL_PLAYER
                
                row.append(cell)
            lines.append(''.join(row))
            
        frame_content = '\n'.join(lines) + '\n' + f'{COLOR_CYAN}{"="*CAMERA_WIDTH}{COLOR_RESET}\n'
        frame_content += f'{COLOR_GREEN}HP: {self.player.hp}/{self.player.max_hp}{COLOR_RESET} | '
        frame_content += f'{COLOR_MAGENTA}Core: {self.core.hp}/{self.core.max_hp}{COLOR_RESET} | '
        frame_content += f'{COLOR_YELLOW}Money: ${self.player.money}{COLOR_RESET} | '
        frame_content += f'{COLOR_RED}Wave: {self.wave}{COLOR_RESET} | Enemies: {len(self.enemies)}\n'
        
        if self.inter_wave_pause:
            frame_content += f'{COLOR_YELLOW}WAVE {self.wave} CLEARED!{COLOR_RESET} (C)ontinue | (S)ave & Continue | Save & E(x)it\n'
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
            return self.show_game_over_menu() if self.game_outcome != "exit" else "exit"
        finally:
            print('\033[?25h', end='', flush=True)
            os.system('cls' if os.name == 'nt' else 'clear')
    
    def show_game_over_menu(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f'\n\n{COLOR_RED}{"="*50}\n{"GAME OVER":^50}\n{"="*50}{COLOR_RESET}\n')
        reason = "The Core has been destroyed!" if self.core.is_dead else "You have been defeated!"
        print(f'{COLOR_RED}{reason}{COLOR_RESET}\n')
        print(f'{COLOR_CYAN}Statistics:{COLOR_RESET}')
        print(f'  Waves Survived: {self.wave}')
        print(f'  Enemies Killed: {self.player.kills}')
        print(f'  Enemy Types Met: {", ".join(sorted(self.encountered_enemy_types))}')
        
        while msvcrt.kbhit(): msvcrt.getch()
        while True:
            print(f'\n{COLOR_YELLOW}Choose an option:{COLOR_RESET}\n  (1) Start New Game')
            if os.path.exists(SAVE_FILE_JSON): print('  (2) Load from Save')
            print('  (3) Exit')
            try:
                choice = msvcrt.getch().decode('utf-8')
                if choice == '1': return 'new_game'
                if choice == '2' and os.path.exists(SAVE_FILE_JSON): return 'continue'
                if choice == '3': return 'exit'
            except UnicodeDecodeError: continue

def show_start_menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f'\n{COLOR_CYAN}{"="*50}\n{"SYSTEM GUARDIAN":^50}\n{"="*50}{COLOR_RESET}\n')
    
    if os.path.exists(SAVE_FILE_JSON):
        print(f'{COLOR_YELLOW}Choose an option:{COLOR_RESET}\n  (1) New Game\n  (2) Continue')
        while True:
            try:
                while msvcrt.kbhit(): msvcrt.getch()
                choice = msvcrt.getch().decode('utf-8')
                if choice in ['1', '2']: return 'new_game' if choice == '1' else 'continue'
            except UnicodeDecodeError: continue
    else:
        print(f'{COLOR_GREEN}Press any key to start a new game...{COLOR_RESET}')
        msvcrt.getch()
        return 'new_game'

def main():
    try:
        next_action = show_start_menu()
        while next_action != 'exit':
            game = Game()
            if next_action == 'continue' and not game.load_game():
                print("Could not load save file. Starting new game.")
                time.sleep(2)
            next_action = game.run()
    except KeyboardInterrupt:
        print('\n\nGame interrupted. Goodbye!')
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        print('\nThanks for playing!')

if __name__ == '__main__':
    main()