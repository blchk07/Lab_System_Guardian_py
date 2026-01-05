import pygame
import random
import math
import sys
import heapq
import json
import os

from settings import *
from utils import Camera
from sprites import Particle, Bullet, Grenade
from entities import (Player, Enemy, ShooterEnemy, ScoutEnemy, EnemySpawner, EnergyNode, PlayerWall, 
                      CryoNode, BonusItem)

class SystemGuardian:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("System Guardian")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 20, bold=True)
        self.map_size = 64
        self.state = "MAIN_MENU" 
        self.return_state = "MAIN_MENU"
        self.overcharge_finish = 0
        
        self.show_fps = False
        self.settings_particles = True
        self.click_handled = False
        
        self.save_file = "savegame.json"
        self.save_exists = os.path.exists(self.save_file)

        self.purchased_weapons = ['PISTOL']
        self.unlocked_weapons = ['PISTOL']
        self.inventory = [{'type': 'WEAPON', 'name': 'PISTOL'}, None, None, None, None]
        self.selected_slot = 0
        self.shop_tab = "WEAPONS"
        self.intermission_time_left = 0 
        self.intermission_duration = 40000 
        
        self.heatmap_dirty = True
        
        self.wave_type = "NORMAL"
        self.survival_time_left = 0
        self.last_survival_spawn = 0

        self.reset()

    def reset(self):
        self.wave = 0
        self.money = 300
        self.overcharge_finish = 0
        self.core_gx, self.core_gy = self.map_size // 2, self.map_size // 2
        self.core_hp = 1000
        self.core_max_hp = 1000
        
        self.damage_multiplier = 1.0
        self.core_defense_mod = 1.0
        self.max_walls_base = 15
        self.max_walls_extra = 0
        self.active_buffs = []
        
        self.enemies = pygame.sprite.Group()
        self.spawners = pygame.sprite.Group()
        self.nodes = pygame.sprite.Group()
        self.player_walls = pygame.sprite.Group()
        self.cryo_nodes = pygame.sprite.Group()
        self.bonuses = pygame.sprite.Group()
        self.bullets = []
        self.particles = []
        self.grenades_list = []
        
        self.inventory = [{'type': 'WEAPON', 'name': 'PISTOL'}, None, None, None, None]
        self.unlocked_weapons = ['PISTOL']
        self.purchased_weapons = ['PISTOL']

        self.stats_damage_dealt = 0
        self.stats_walls_built = 0
        self.max_enemies_cap = 35 
        
        self.wave_type = "NORMAL"

        self.generate_map()
        self.build_map_surface()
        
        self.heatmap_dirty = True
        self.player = Player(self.core_gx + 2, self.core_gy + 2)
        self.camera = Camera(self.map_size * TILE_SIZE, self.map_size * TILE_SIZE)
        self.last_shot_time = 0
        self.core_under_attack_timer = 0

    def trigger_overcharge(self):
        duration = random.randint(15000, 25000)
        self.overcharge_finish = pygame.time.get_ticks() + duration

    def generate_map(self):
        self.walls = {}
        for _ in range(self.map_size * self.map_size // 7):
            gx, gy = random.randint(1, self.map_size-2), random.randint(1, self.map_size-2)
            if abs(gx - self.core_gx) > 5 or abs(gy - self.core_gy) > 5:
                self.walls[(gx, gy)] = True

    def build_map_surface(self):
        self.map_surface = pygame.Surface((self.map_size * TILE_SIZE, self.map_size * TILE_SIZE))
        self.map_surface.fill(COLOR_BG)
        for gy in range(self.map_size):
            for gx in range(self.map_size):
                r = pygame.Rect(gx*TILE_SIZE, gy*TILE_SIZE, TILE_SIZE, TILE_SIZE)
                if (gx, gy) in self.walls:
                    pygame.draw.rect(self.map_surface, COLOR_WALL, r)
                else:
                    pygame.draw.rect(self.map_surface, COLOR_FLOOR, r, 1)

    def is_tile_blocked(self, gx, gy):
        if (gx, gy) in self.walls: return True
        for struct in list(self.spawners) + list(self.nodes) + list(self.player_walls) + list(self.cryo_nodes):
            if int(struct.grid_pos.x) == gx and int(struct.grid_pos.y) == gy:
                return True
        return False

    def is_position_safe_for_spawn(self, gx, gy):
        if self.is_tile_blocked(gx, gy): return False
        for b in self.bonuses:
            if int(b.grid_pos.x) == gx and int(b.grid_pos.y) == gy:
                return False
        return True

    def get_player_wall_at(self, gx, gy):
        for wall in self.player_walls:
            if int(wall.grid_pos.x) == gx and int(wall.grid_pos.y) == gy:
                return wall
        return None
    
    def get_cryo_at(self, gx, gy):
        for c in self.cryo_nodes:
            if int(c.grid_pos.x) == gx and int(c.grid_pos.y) == gy:
                return c
        return None

    def update_heatmap(self):
        target = (self.core_gx, self.core_gy)
        pq = [(0, target)]
        self.heatmap = {target: 0}
        
        while pq:
            dist, curr = heapq.heappop(pq)
            if dist > self.heatmap.get(curr, 9999): continue
            
            for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                nx, ny = curr[0] + dx, curr[1] + dy
                
                if 0 <= nx < self.map_size and 0 <= ny < self.map_size:
                    is_structure_obstacle = False
                    for s in list(self.spawners) + list(self.nodes):
                        if int(s.grid_pos.x) == nx and int(s.grid_pos.y) == ny:
                            is_structure_obstacle = True
                            break

                    if (nx, ny) not in self.walls and not is_structure_obstacle:
                        
                        cost = 1
                        if self.get_player_wall_at(nx, ny): cost = 30
                        
                        for cryo in self.cryo_nodes:
                            if abs(nx - cryo.grid_pos.x) + abs(ny - cryo.grid_pos.y) <= cryo.radius:
                                cost += 5 
                                break
                        
                        new_dist = dist + cost
                        if new_dist < self.heatmap.get((nx, ny), 9999):
                            self.heatmap[(nx, ny)] = new_dist
                            heapq.heappush(pq, (new_dist, (nx, ny)))

    def start_intermission(self, is_new_checkpoint=False):
        self.state = "INTERMISSION"
        self.intermission_time_left = self.intermission_duration
        self.bonuses.empty()
        
        if len(self.unlocked_weapons) < 3: self._spawn_special_crate()
        
        if is_new_checkpoint:
            self.save_game()

    def spawn_wave(self):
        self.state = "PLAYING"
        self.wave += 1
        
        if self.wave % 5 == 0:
            self.wave_type = "SURVIVAL"
            self.survival_time_left = 60000 
            self.max_enemies_cap = 60 
            self.last_survival_spawn = pygame.time.get_ticks()
            for _ in range(10): self._add_enemy(Enemy, {'speed': 400, 'hp': 50 + self.wave * 10, 'damage': 6})
        else:
            self.wave_type = "NORMAL"
            self.max_enemies_cap = 35
            
            total = 7 + self.wave * 2
            shooters = min(self.wave // 2, 12)
            speed = max(380, 1100 - (self.wave * 40))
            stats = {'speed': speed, 'hp': 50 + self.wave * 15, 'damage': 6 + self.wave}
            for _ in range(total - shooters): self._add_enemy(Enemy, stats)
            for _ in range(shooters): self._add_enemy(ShooterEnemy, stats)
        
        self._spawn_bonus() 
        if self.wave % 2 == 0: self._spawn_bonus()
        
        if self.wave >= 4 and random.random() < 0.6 and len(self.spawners) < 2:
            self._spawn_structure(EnemySpawner, 18, 28)
        if self.wave >= 3 and random.random() < 0.4 and len(self.nodes) < 1:
            self._spawn_structure(EnergyNode, 14, 24)
            
        if random.random() < 0.5:
            self._spawn_buff()

    def _add_enemy(self, cls, stats):
        if len(self.enemies) >= self.max_enemies_cap: return
        for _ in range(25):
            gx, gy = random.randint(0, self.map_size-1), random.choice([0, self.map_size-1])
            if random.random() > 0.5: gx, gy = random.choice([0, self.map_size-1]), random.randint(0, self.map_size-1)
            if not self.is_tile_blocked(gx, gy):
                self.enemies.add(cls(gx, gy, stats))
                break

    def _spawn_bonus(self):
        for _ in range(60):
            gx, gy = self.core_gx + random.randint(-8, 8), self.core_gy + random.randint(-8, 8)
            if 0 <= gx < self.map_size and 0 <= gy < self.map_size:
                if self.is_position_safe_for_spawn(gx, gy) and abs(gx-self.core_gx) > 2:
                    rand = random.random()
                    if rand < 0.4: self.bonuses.add(BonusItem(gx, gy, "HEALTH"))
                    elif rand < 0.7: self.bonuses.add(BonusItem(gx, gy, "GRENADE_BOX"))
                    else: self.bonuses.add(BonusItem(gx, gy, "CORE_REPAIR"))
                    break

    def _spawn_special_crate(self):
        for _ in range(100):
            gx = random.randint(5, self.map_size - 5)
            gy = random.randint(5, self.map_size - 5)
            if self.is_position_safe_for_spawn(gx, gy) and abs(gx - self.core_gx) > 20:
                self.bonuses.add(BonusItem(gx, gy, "WEAPON_CRATE"))
                break

    def _spawn_buff(self):
        for _ in range(50):
            gx = random.randint(10, self.map_size - 10)
            gy = random.randint(10, self.map_size - 10)
            if self.is_position_safe_for_spawn(gx, gy) and abs(gx - self.core_gx) > 5:
                b_type = random.choice(['BUFF_DMG', 'BUFF_DEF', 'BUFF_WALL'])
                self.bonuses.add(BonusItem(gx, gy, b_type))
                break

    def _spawn_structure(self, cls, min_d, max_d):
        for _ in range(150):
            gx, gy = random.randint(5, self.map_size-6), random.randint(5, self.map_size-6)
            dist = abs(gx - self.core_gx) + abs(gy - self.core_gy)
            if min_d <= dist <= max_d and not self.is_tile_blocked(gx, gy):
                obj = cls(gx, gy)
                if cls == EnemySpawner: self.spawners.add(obj)
                else: self.nodes.add(obj)
                self.update_heatmap()
                break

    def save_game(self):
        data = {
            "wave": self.wave,
            "money": self.money,
            "core_hp": self.core_hp,
            "player_hp": self.player.hp,
            "inventory": self.inventory,
            "unlocked_weapons": self.unlocked_weapons,
            "purchased_weapons": self.purchased_weapons,
            "stats": {"dmg": self.stats_damage_dealt, "walls": self.stats_walls_built},
            "buffs": {"dmg_mult": self.damage_multiplier, "core_def": self.core_defense_mod, "max_walls": self.max_walls_extra, "active_list": self.active_buffs}
        }
        with open(self.save_file, "w") as f:
            json.dump(data, f)
        self.save_exists = True

    def load_game(self):
        if not os.path.exists(self.save_file): return False
        try:
            with open(self.save_file, "r") as f:
                data = json.load(f)
            self.reset()
            self.wave = data["wave"]
            self.money = data["money"]
            self.core_hp = data["core_hp"]
            self.player.hp = data["player_hp"]
            
            loaded_inv = data["inventory"]
            for i in range(len(loaded_inv)):
                item = loaded_inv[i]
                if item and item.get('type') == 'WEAPON':
                    if item.get('name') not in WEAPON_STATS:
                        loaded_inv[i] = {'type': 'WEAPON', 'name': 'PISTOL'} 
            self.inventory = loaded_inv

            self.unlocked_weapons = data.get("unlocked_weapons", ['PISTOL'])
            self.purchased_weapons = data.get("purchased_weapons", ['PISTOL'])
            self.stats_damage_dealt = data["stats"]["dmg"]
            self.stats_walls_built = data["stats"]["walls"]
            self.damage_multiplier = data["buffs"]["dmg_mult"]
            self.core_defense_mod = data["buffs"]["core_def"]
            self.max_walls_extra = data["buffs"]["max_walls"]
            self.active_buffs = data["buffs"]["active_list"]
            
            self.start_intermission(is_new_checkpoint=False)
            return True
        except Exception as e:
            print(f"Save Load Error: {e}")
            return False

    def add_to_inventory(self, item_type, count=1, name=None):
        for slot in self.inventory:
            if slot and slot['type'] == item_type and slot.get('name') == name:
                slot['count'] += count
                return True
        start_idx = 2
        if item_type == 'WEAPON': return False 
        for i in range(start_idx, 5):
            if self.inventory[i] is None:
                self.inventory[i] = {'type': item_type, 'count': count}
                if name: self.inventory[i]['name'] = name
                return True
        return False

    def equip_weapon_logic(self, weapon_name, target_slot):
        if target_slot not in [0, 1]: return False
        
        other_slot = 1 if target_slot == 0 else 0
        current_in_target = self.inventory[target_slot]
        current_in_other = self.inventory[other_slot]

        if current_in_target and current_in_target.get('name') == weapon_name:
            return False

        if current_in_other and current_in_other.get('name') == weapon_name:
            self.inventory[target_slot], self.inventory[other_slot] = self.inventory[other_slot], self.inventory[target_slot]
            return True

        self.inventory[target_slot] = {'type': 'WEAPON', 'name': weapon_name}
        return True

    def attempt_buy_or_equip_weapon(self, weapon_name, cost, target_slot):
        if weapon_name not in self.unlocked_weapons: return False

        if weapon_name in self.purchased_weapons:
            return self.equip_weapon_logic(weapon_name, target_slot)
        
        if self.money >= cost:
            self.money -= cost
            self.purchased_weapons.append(weapon_name)
            return self.equip_weapon_logic(weapon_name, target_slot)
        
        return False

    def buy_item(self, category, item_id, cost, target_slot=None):
        success = False
        
        if category == "WEAPONS":
            if target_slot is not None:
                success = self.attempt_buy_or_equip_weapon(item_id, cost, target_slot)
                return success 
                
        elif self.money >= cost:
            if category == "DEFENSE":
                if item_id == "WALL": success = self.add_to_inventory('WALL', 1)
                elif item_id == "CRYO": success = self.add_to_inventory('CRYO', 1)
            elif category == "UTILITY":
                if item_id == "GRENADE": success = self.add_to_inventory('GRENADE', 1)
                elif item_id == "HP": 
                    self.player.hp = min(self.player.max_hp, self.player.hp + 50)
                    success = True
                elif item_id == "CORE":
                    self.core_hp = min(self.core_max_hp, self.core_hp + 100)
                    success = True
            
            if success: self.money -= cost
            
        return success

    def swap_weapons(self):
        self.inventory[0], self.inventory[1] = self.inventory[1], self.inventory[0]

    def build_wall(self, gx, gy):
        selected_item = self.inventory[self.selected_slot]
        if selected_item and selected_item['type'] == 'WALL' and selected_item['count'] > 0:
            limit = self.max_walls_base + self.max_walls_extra
            if len(self.player_walls) < limit:
                dist = abs(gx - self.player.grid_pos.x) + abs(gy - self.player.grid_pos.y)
                if dist <= 3 and not self.is_tile_blocked(gx, gy) and (gx, gy) != (self.core_gx, self.core_gy):
                    wall = PlayerWall(gx, gy)
                    self.player_walls.add(wall)
                    self.heatmap_dirty = True
                    selected_item['count'] -= 1
                    self.stats_walls_built += 1
                    if selected_item['count'] <= 0:
                        self.inventory[self.selected_slot] = None

    def place_cryo(self, gx, gy):
        selected_item = self.inventory[self.selected_slot]
        if selected_item and selected_item['type'] == 'CRYO' and selected_item['count'] > 0:
             if len(self.cryo_nodes) < 5:
                dist = abs(gx - self.player.grid_pos.x) + abs(gy - self.player.grid_pos.y)
                if dist <= 3 and not self.is_tile_blocked(gx, gy) and (gx, gy) != (self.core_gx, self.core_gy):
                    node = CryoNode(gx, gy)
                    self.cryo_nodes.add(node)
                    self.heatmap_dirty = True
                    selected_item['count'] -= 1
                    if selected_item['count'] <= 0:
                        self.inventory[self.selected_slot] = None

    def throw_grenade(self, target_pos):
        selected_item = self.inventory[self.selected_slot]
        if selected_item and selected_item['type'] == 'GRENADE' and selected_item['count'] > 0:
            start_pos = self.player.rect.center
            self.grenades_list.append(Grenade(start_pos[0], start_pos[1], target_pos[0], target_pos[1]))
            selected_item['count'] -= 1
            if selected_item['count'] <= 0:
                self.inventory[self.selected_slot] = None

    def shoot_weapon(self):
        item = self.inventory[self.selected_slot]
        if not item or item['type'] != 'WEAPON': return
        if item['name'] not in WEAPON_STATS: return 

        w_stats = WEAPON_STATS[item['name']]
        now = pygame.time.get_ticks()
        
        if now - self.last_shot_time > w_stats['rate']:
            self.last_shot_time = now
            m_pos = pygame.mouse.get_pos()
            wt = pygame.Vector2(m_pos[0] - self.camera.camera.x, m_pos[1] - self.camera.camera.y)
            base_angle = math.atan2(wt.y - self.player.rect.centery, wt.x - self.player.rect.centerx)
            
            final_dmg = w_stats['damage'] * self.damage_multiplier

            for _ in range(w_stats['count']):
                spread = random.uniform(-w_stats['spread'], w_stats['spread'])
                angle = base_angle + spread
                self.bullets.append(Bullet(
                    self.player.rect.centerx, self.player.rect.centery, angle, 
                    damage=final_dmg, 
                    speed=w_stats['speed'],
                    max_dist=w_stats['range'],
                    color=w_stats['color']
                ))

    def check_shop_proximity(self):
        core_pos = pygame.Vector2(self.core_gx * TILE_SIZE, self.core_gy * TILE_SIZE)
        player_pos = self.player.pixel_pos
        distance = player_pos.distance_to(core_pos)
        return distance <= 200

    def draw_button(self, text, x, y, w, h, hover_color=COLOR_BUTTON_HOVER, default_color=COLOR_BUTTON, active=False, disabled=False):
        mx, my = pygame.mouse.get_pos()
        rect = pygame.Rect(x, y, w, h)
        clicked = False
        color = default_color
        
        if disabled: color = COLOR_BUTTON_DISABLED
        elif active: color = COLOR_TAB_ACTIVE
        elif rect.collidepoint(mx, my):
            color = hover_color
            if pygame.mouse.get_pressed()[0] and not self.click_handled:
                clicked = True
                self.click_handled = True

        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_UI_BORDER, rect, 2, border_radius=8)
        text_surf = self.font.render(text, True, COLOR_BUTTON_TEXT)
        text_rect = text_surf.get_rect(center=rect.center)
        self.screen.blit(text_surf, text_rect)
        return clicked and not disabled

    def handle_input(self):
        now = pygame.time.get_ticks()
        if not pygame.mouse.get_pressed()[0]: self.click_handled = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if self.state == "PLAYING" or self.state == "INTERMISSION":
                    if event.key == pygame.K_ESCAPE: 
                        self.return_state = self.state 
                        self.state = "PAUSED"
                    if event.key == pygame.K_b and self.check_shop_proximity():
                        self.return_state = self.state 
                        self.state = "SHOP"
                    
                    if event.key == pygame.K_1: self.selected_slot = 0
                    if event.key == pygame.K_2: self.selected_slot = 1
                    if event.key == pygame.K_3: self.selected_slot = 2
                    if event.key == pygame.K_4: self.selected_slot = 3
                    if event.key == pygame.K_5: self.selected_slot = 4
                    if self.state == "INTERMISSION" and event.key == pygame.K_SPACE:
                        self.spawn_wave() 

                elif self.state == "PAUSED" and event.key == pygame.K_ESCAPE: self.state = self.return_state
                elif self.state == "SHOP":
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_b: self.state = self.return_state

        keys = pygame.key.get_pressed()
        if self.state in ["PLAYING", "INTERMISSION"]:
            if now - self.player.last_move_time > self.player.move_delay:
                m = False
                if keys[pygame.K_w]: m = self.player.move_to(0, -1, self)
                elif keys[pygame.K_s]: m = self.player.move_to(0, 1, self)
                elif keys[pygame.K_a]: m = self.player.move_to(-1, 0, self)
                elif keys[pygame.K_d]: m = self.player.move_to(1, 0, self)
                if m: self.player.last_move_time = now
            
            if self.state == "PLAYING" and pygame.mouse.get_pressed()[0] and not self.click_handled:
                selected = self.inventory[self.selected_slot]
                if selected:
                    m_pos = pygame.mouse.get_pos()
                    if selected['type'] == 'WEAPON':
                        self.shoot_weapon()
                    elif selected['type'] == 'WALL':
                        gx, gy = int((m_pos[0]-self.camera.camera.x)//TILE_SIZE), int((m_pos[1]-self.camera.camera.y)//TILE_SIZE)
                        if now - self.last_shot_time > 200: self.build_wall(gx, gy); self.last_shot_time = now
                    elif selected['type'] == 'CRYO':
                        gx, gy = int((m_pos[0]-self.camera.camera.x)//TILE_SIZE), int((m_pos[1]-self.camera.camera.y)//TILE_SIZE)
                        if now - self.last_shot_time > 200: self.place_cryo(gx, gy); self.last_shot_time = now
                    elif selected['type'] == 'GRENADE':
                        if now - self.last_shot_time > 1000:
                            target = pygame.Vector2(m_pos[0] - self.camera.camera.x, m_pos[1] - self.camera.camera.y)
                            self.throw_grenade(target)
                            self.last_shot_time = now

    def update_bullets(self):
        for b in self.bullets[:]:
            b.update(self.walls)
            if not b.active: self.bullets.remove(b); continue
            
            wall_hit = False
            for w in list(self.player_walls) + list(self.cryo_nodes):
                if w.rect.colliderect(b.rect): 
                    w.hp -= 25 
                    wall_hit = True
                    break 
            if wall_hit:
                self.bullets.remove(b)
                continue

            if b.is_enemy:
                if self.player.rect.colliderect(b.rect): self.player.hp -= 10; self.bullets.remove(b)
                elif pygame.Rect(self.core_gx*TILE_SIZE, self.core_gy*TILE_SIZE, TILE_SIZE, TILE_SIZE).colliderect(b.rect):
                    self.core_hp -= 7 * self.core_defense_mod; self.bullets.remove(b); self.core_under_attack_timer = pygame.time.get_ticks() + 1000
            else:
                h = False
                for e in list(self.enemies) + list(self.spawners) + list(self.nodes):
                    if e.rect.colliderect(b.rect):
                        actual_dmg = min(e.hp, b.damage)
                        e.hp -= actual_dmg
                        self.stats_damage_dealt += actual_dmg
                        h = True
                        if e.hp <= 0:
                            if hasattr(e, 'reward'): self.money += e.reward
                            if not isinstance(e, EnergyNode): e.kill()
                            if isinstance(e, (EnemySpawner, EnergyNode)): self.heatmap_dirty = True
                        break
                if h: self.bullets.remove(b)

    def update(self):
        dt = self.clock.get_time()
        now = pygame.time.get_ticks()
        
        if self.heatmap_dirty:
            self.update_heatmap()
            self.heatmap_dirty = False

        self.update_bullets()
        if self.settings_particles: 
            self.particles = [p for p in self.particles if p.update()]
        
        if self.state == "INTERMISSION":
            self.intermission_time_left -= dt
            if self.intermission_time_left <= 0:
                self.spawn_wave()
            self.player.update_animation()
            self.camera.update(self.player)
            for b in list(self.bonuses):
                picked_up = self.player.rect.colliderect(b.rect) or (int(self.player.grid_pos.x) == int(b.grid_pos.x) and int(self.player.grid_pos.y) == int(b.grid_pos.y))
                if picked_up:
                    if b.type == "WEAPON_CRATE":
                        remaining = [w for w in WEAPON_STATS.keys() if w not in self.unlocked_weapons]
                        if remaining:
                            new_w = random.choice(remaining)
                            self.unlocked_weapons.append(new_w)
                            print(f"Unlocked: {new_w}")
                    elif b.type.startswith("BUFF"):
                         if b.type == 'BUFF_DMG': self.damage_multiplier += 0.1; self.active_buffs.append("DMG +10%")
                         elif b.type == 'BUFF_DEF': self.core_defense_mod = max(0.5, self.core_defense_mod - 0.1); self.active_buffs.append("CORE DEF +10%")
                         elif b.type == 'BUFF_WALL': self.max_walls_extra += 1; self.active_buffs.append("WALL +1")
                    elif b.type == "HEALTH": self.player.hp = min(self.player.max_hp, self.player.hp + 70)
                    elif b.type == "GRENADE_BOX": self.add_to_inventory('GRENADE', 3)
                    elif b.type == "CORE_REPAIR": self.core_hp = min(self.core_max_hp, self.core_hp + 150)
                    b.kill()
            return

        if self.state != "PLAYING": return

        self.player.update_animation()
        self.camera.update(self.player)
        
        for b in list(self.bonuses):
            picked_up = self.player.rect.colliderect(b.rect) or (int(self.player.grid_pos.x) == int(b.grid_pos.x) and int(self.player.grid_pos.y) == int(b.grid_pos.y))
            if picked_up:
                if b.type == "WEAPON_CRATE":
                    remaining = [w for w in WEAPON_STATS.keys() if w not in self.unlocked_weapons]
                    if remaining: self.unlocked_weapons.append(random.choice(remaining))
                elif b.type.startswith("BUFF"):
                     if b.type == 'BUFF_DMG': self.damage_multiplier += 0.1; self.active_buffs.append("DMG +10%")
                     elif b.type == 'BUFF_DEF': self.core_defense_mod = max(0.5, self.core_defense_mod - 0.1); self.active_buffs.append("CORE DEF +10%")
                     elif b.type == 'BUFF_WALL': self.max_walls_extra += 1; self.active_buffs.append("WALL +1")
                elif b.type == "HEALTH": self.player.hp = min(self.player.max_hp, self.player.hp + 70)
                elif b.type == "GRENADE_BOX": self.add_to_inventory('GRENADE', 3)
                elif b.type == "CORE_REPAIR": self.core_hp = min(self.core_max_hp, self.core_hp + 150)
                b.kill()
        
        for g in self.grenades_list[:]:
            if g.update():
                if self.settings_particles:
                    for _ in range(20): self.particles.append(Particle(g.pos.x, g.pos.y, COLOR_EXPLOSION, speed_mult=2.5, decay_speed=15))
                blast_rect = pygame.Rect(g.pos.x - g.blast_radius, g.pos.y - g.blast_radius, g.blast_radius*2, g.blast_radius*2)
                for e in list(self.enemies):
                    if e.rect.colliderect(blast_rect):
                        if g.pos.distance_to(pygame.Vector2(e.rect.center)) <= g.blast_radius:
                            dmg = min(e.hp, g.damage * self.damage_multiplier)
                            e.hp -= dmg
                            self.stats_damage_dealt += dmg
                            if e.hp <= 0: self.money += e.reward; e.kill()
                for s in list(self.spawners):
                    if s.rect.colliderect(blast_rect):
                         s.hp -= g.damage * self.damage_multiplier
                         if s.hp <= 0: self.money += s.reward; s.kill(); self.update_heatmap()
                self.grenades_list.remove(g)

        is_overcharged = now < self.overcharge_finish
        core_mod = 0.5 if len(self.nodes) > 0 else 1.0
        if is_overcharged: core_mod = 0
        core_mod *= self.core_defense_mod 
        
        for w in list(self.player_walls) + list(self.cryo_nodes):
            if now - w.spawn_time > w.lifetime or w.hp <= 0: w.kill(); self.heatmap_dirty = True

        if self.wave_type == "SURVIVAL":
            self.survival_time_left -= dt

            if now - self.last_survival_spawn > 2000:
                self._add_enemy(Enemy, {'speed': 400, 'hp': 50 + self.wave * 5, 'damage': 6})
                self.last_survival_spawn = now
                
            if self.survival_time_left <= 0:
                self.money += 500 
                for e in self.enemies: e.kill() 
                self.start_intermission(is_new_checkpoint=True)
                return

        else:
            for s in self.spawners:
                if s.scouts_produced < s.max_scouts and now - s.last_spawn > s.spawn_delay:
                    spawn_tile = s.get_adjacent_free_tile(self)
                    if spawn_tile:
                        self.enemies.add(ScoutEnemy(spawn_tile[0], spawn_tile[1], {'hp':40, 'speed':450, 'damage':2.5}))
                        s.scouts_produced += 1
                        s.last_spawn = now
                        s._redraw()
                if s.hp <= 0: s.kill(); self.money += s.reward; self.heatmap_dirty = True
            
            if len(self.enemies) == 0 and len(self.spawners) == 0:
                self.start_intermission(is_new_checkpoint=True)
                return

        for n in list(self.nodes):
            if n.hp <= 0: n.kill(); self.money += n.reward; self.heatmap_dirty = True; self.trigger_overcharge()
        
        for e in self.enemies:
            e.ai_logic(self.player.grid_pos.x, self.player.grid_pos.y, self.heatmap, self)
            e.update_animation()
            if isinstance(e, ShooterEnemy):
                eb = e.try_shoot(pygame.Vector2(self.player.rect.center))
                if eb: self.bullets.append(eb)
            
            if e.grid_pos == pygame.Vector2(self.core_gx, self.core_gy): 
                self.core_hp -= e.damage * core_mod
                self.core_under_attack_timer = now + 1000 
            elif e.grid_pos == self.player.grid_pos: 
                self.player.hp -= 0.5
        
        if self.player.hp <= 0 or self.core_hp <= 0: self.state = "GAMEOVER"

    def draw(self):
        self.screen.fill(COLOR_BG)
        
        if self.state in ["PLAYING", "PAUSED", "SHOP", "GAMEOVER", "INTERMISSION"]:
            self._draw_game()

        if self.state == "MAIN_MENU": self.draw_main_menu()
        elif self.state == "SETTINGS": self.draw_settings_menu()
        elif self.state == "PAUSED": self._draw_overlay_bg(); self.draw_pause_menu()
        elif self.state == "SHOP": self.draw_shop()
        elif self.state == "GAMEOVER": self._draw_overlay_bg(); self.draw_gameover()
        if self.state == "INTERMISSION": self.draw_intermission_hud()
            
        if self.show_fps: self.draw_text(f"FPS: {int(self.clock.get_fps())}", 16, 40, 10, (0, 255, 0))
        pygame.display.flip()

    def _draw_game(self):
        self.screen.blit(self.map_surface, self.camera.camera)
        
        cr = self.camera.camera
        now = pygame.time.get_ticks()
        is_overcharged = now < self.overcharge_finish
        
        core_r = pygame.Rect(self.core_gx * TILE_SIZE, self.core_gy * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        core_color = COLOR_CORE if not is_overcharged else COLOR_OVERCHARGE
        pygame.draw.rect(self.screen, core_color, self.camera.apply_rect(core_r), border_radius=10)
        
        for c in self.cryo_nodes:
            c.draw_range(self.screen, self.camera)

        for g in [self.spawners, self.nodes, self.cryo_nodes, self.player_walls, self.enemies, self.bonuses]:
            for e in g:
                self.screen.blit(e.image, self.camera.apply(e))
                if hasattr(e, 'draw_hp_bar'): e.draw_hp_bar(self.screen, self.camera)

        for g in self.grenades_list:
            pos = self.camera.apply_rect(pygame.Rect(g.pos.x-4, g.pos.y-4, 8, 8))
            pygame.draw.circle(self.screen, COLOR_GRENADE, pos.center, 5)

        self.screen.blit(self.player.image, self.camera.apply(self.player))
        for b in self.bullets:
            pygame.draw.circle(self.screen, b.color, self.camera.apply_rect(b.rect).center, 3)
        
        for p in self.particles: p.draw(self.screen, self.camera)

        cur_item = self.inventory[self.selected_slot]
        if self.state == "PLAYING" and cur_item:
            mx, my = pygame.mouse.get_pos()
            if cur_item['type'] == 'GRENADE':
                player_screen_pos = self.camera.apply_rect(self.player.rect).center
                pygame.draw.circle(self.screen, (100, 255, 100), player_screen_pos, 300, 1) 
                m_vec = pygame.Vector2(mx, my)
                p_vec = pygame.Vector2(player_screen_pos)
                dist_vec = m_vec - p_vec
                if dist_vec.length() > 300: m_vec = p_vec + dist_vec.normalize() * 300
                pygame.draw.circle(self.screen, (255, 100, 100), (int(m_vec.x), int(m_vec.y)), 160, 1)
            elif cur_item['type'] == 'CRYO':
                 gx, gy = int((mx-self.camera.camera.x)//TILE_SIZE), int((my-self.camera.camera.y)//TILE_SIZE)
                 center = self.camera.apply_rect(pygame.Rect(gx*TILE_SIZE, gy*TILE_SIZE, TILE_SIZE, TILE_SIZE)).center
                 pygame.draw.circle(self.screen, COLOR_CRYO_ZONE, center, (2 * TILE_SIZE) + (TILE_SIZE // 2), 2)

        if self.state in ["PLAYING", "INTERMISSION"] and self.check_shop_proximity():
            self.draw_text("PRESS [B] FOR SHOP", 20, SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 100, (255, 255, 0))
        
        if self.wave_type == "SURVIVAL" and self.state == "PLAYING":
             rem = max(0, int(self.survival_time_left / 1000))
             self.draw_text(f"SURVIVE: {rem}s", 40, SCREEN_WIDTH//2, 80, COLOR_SURVIVAL)

        if now < self.core_under_attack_timer:
            if (now // 200) % 2 == 0: 
                self.draw_text("!!! CORE UNDER ATTACK !!!", 30, SCREEN_WIDTH//2, 100, COLOR_WARNING)

        self.draw_ui()
        self.draw_inventory()

    def _draw_overlay_bg(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

    def draw_main_menu(self):
        self.draw_text("SYSTEM GUARDIAN", 60, SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 140, COLOR_CORE)
        bw, bh = 250, 50
        cx = SCREEN_WIDTH // 2 - bw // 2
        cy = SCREEN_HEIGHT // 2 - 40
        spacing = 60

        if self.draw_button("NEW GAME", cx, cy, bw, bh):
            self.reset()
            self.start_intermission()
        
        if self.save_exists:
            if self.draw_button("CONTINUE", cx, cy + spacing, bw, bh):
                if self.load_game(): pass 
        
        if self.draw_button("SETTINGS", cx, cy + spacing * 2, bw, bh):
            self.prev_state = "MAIN_MENU"
            self.state = "SETTINGS"

        if self.draw_button("EXIT GAME", cx, cy + spacing * 3, bw, bh):
            pygame.quit(); sys.exit()

    def draw_intermission_hud(self):
        remaining = max(0, int(self.intermission_time_left / 1000))
        color = (255, 255, 0)
        
        if (self.wave + 1) % 5 == 0:
             self.draw_text("NEXT WAVE: SURVIVAL MODE!", 30, SCREEN_WIDTH//2, 60, COLOR_SURVIVAL)
             color = COLOR_SURVIVAL

        self.draw_text(f"NEXT WAVE IN: {remaining}s", 40, SCREEN_WIDTH//2, 100, color)
        self.draw_text("PREPARE DEFENSES | PRESS [SPACE] TO SKIP", 20, SCREEN_WIDTH//2, 140, COLOR_TEXT)
        if remaining <= 5:
            self.draw_text("WARNING: WAVE INCOMING", 30, SCREEN_WIDTH//2, 180, COLOR_WARNING)

    def draw_pause_menu(self):
        self.draw_text("PAUSED", 50, SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 140, COLOR_TEXT)
        bw, bh = 250, 50
        cx = SCREEN_WIDTH // 2 - bw // 2
        cy = SCREEN_HEIGHT // 2 - 40
        spacing = 60
        if self.draw_button("CONTINUE", cx, cy, bw, bh): self.state = self.return_state
        if self.draw_button("SETTINGS", cx, cy + spacing, bw, bh): self.prev_state = "PAUSED"; self.state = "SETTINGS"
        if self.draw_button("MAIN MENU", cx, cy + spacing * 2, bw, bh): self.state = "MAIN_MENU"
        if self.draw_button("EXIT GAME", cx, cy + spacing * 3, bw, bh): pygame.quit(); sys.exit()

    def draw_settings_menu(self):
        self.screen.fill(COLOR_BG)
        self.draw_text("SETTINGS", 50, SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 120, COLOR_TEXT)
        bw, bh = 300, 50
        cx = SCREEN_WIDTH // 2 - bw // 2
        cy = SCREEN_HEIGHT // 2 - 40
        spacing = 60
        fps_text = f"SHOW FPS: {'ON' if self.show_fps else 'OFF'}"
        if self.draw_button(fps_text, cx, cy, bw, bh): self.show_fps = not self.show_fps
        part_text = f"PARTICLES: {'ON' if self.settings_particles else 'OFF'}"
        if self.draw_button(part_text, cx, cy + spacing, bw, bh): self.settings_particles = not self.settings_particles
        if self.draw_button("BACK", cx, cy + spacing * 2, bw, bh): self.state = self.prev_state

    def draw_gameover(self):
        self.draw_text("CORE BREACHED", 60, SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 140, COLOR_ENEMY)
        self.draw_text(f"WAVES SURVIVED: {self.wave}", 24, SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 80, COLOR_TEXT)
        self.draw_text(f"DAMAGE DEALT: {int(self.stats_damage_dealt)}", 24, SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 50, COLOR_TEXT)
        self.draw_text(f"WALLS BUILT: {self.stats_walls_built}", 24, SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 20, COLOR_TEXT)

        bw, bh = 250, 50
        cx = SCREEN_WIDTH // 2 - bw // 2
        cy = SCREEN_HEIGHT // 2 + 40
        spacing = 60
        
        if self.draw_button("TRY AGAIN", cx, cy, bw, bh):
            self.reset()
            self.start_intermission()
        
        if self.save_exists:
            if self.draw_button("LOAD LAST SAVE", cx, cy + spacing, bw, bh):
                if self.load_game(): pass
        
        if self.draw_button("MAIN MENU", cx, cy + spacing * 2, bw, bh):
            self.state = "MAIN_MENU"

    def draw_ui(self):
        now = pygame.time.get_ticks()
        is_overcharged = now < self.overcharge_finish
        
        pygame.draw.rect(self.screen, (40, 40, 40), (20, 20, 260, 22))
        pygame.draw.rect(self.screen, COLOR_CORE if not is_overcharged else COLOR_OVERCHARGE, (20, 20, 260 * (max(0, self.core_hp)/1000), 22))
        self.draw_text(f"CORE: {int(max(0, self.core_hp))}/1000", 16, 150, 31)
        
        pygame.draw.rect(self.screen, (40, 40, 40), (20, 48, 160, 12))
        pygame.draw.rect(self.screen, COLOR_PLAYER, (20, 48, 160 * (max(0, self.player.hp)/200), 12))
        self.draw_text(f"{int(max(0, self.player.hp))}/200", 10, 100, 54, (255,255,255))
        
        self.draw_text(f"WAVE: {self.wave}", 22, SCREEN_WIDTH - 110, 32)
        self.draw_text(f"CASH: ${self.money}", 22, SCREEN_WIDTH - 110, 62, (0, 255, 0))

        if self.active_buffs:
            self.draw_text("ACTIVE BUFFS:", 14, SCREEN_WIDTH - 80, 100, (200, 200, 200))
            buff_counts = {}
            for buff in self.active_buffs:
                buff_counts[buff] = buff_counts.get(buff, 0) + 1
            
            y_offset = 120
            for buff, count in buff_counts.items():
                text_display = f"{buff} x{count}" if count > 1 else buff
                self.draw_text(text_display, 12, SCREEN_WIDTH - 80, y_offset, COLOR_BUFF)
                y_offset += 15

    def draw_inventory(self):
        slot_size = 60
        gap = 10
        start_x = (SCREEN_WIDTH - (5 * slot_size + 4 * gap)) // 2
        y = SCREEN_HEIGHT - slot_size - 20

        for i in range(5):
            x = start_x + i * (slot_size + gap)
            rect = pygame.Rect(x, y, slot_size, slot_size)
            border_color = COLOR_UI_SELECTED if i == self.selected_slot else COLOR_UI_BORDER
            pygame.draw.rect(self.screen, COLOR_UI_BG, rect)
            pygame.draw.rect(self.screen, border_color, rect, 3)
            self.draw_text(str(i+1), 12, x + 10, y + 10, (150, 150, 150))
            item = self.inventory[i]
            if item:
                if item['type'] == 'WEAPON':
                    w_name = item.get('name', 'PISTOL')
                    color = WEAPON_STATS.get(w_name, WEAPON_STATS['PISTOL'])['color']
                    pygame.draw.circle(self.screen, color, (x + slot_size//2, y + slot_size//2), 10)
                    self.draw_text(w_name[:3], 12, x + slot_size//2, y + slot_size - 10)
                elif item['type'] == 'WALL':
                    pygame.draw.rect(self.screen, COLOR_PLAYER_WALL, (x + 15, y + 15, slot_size-30, slot_size-30))
                    self.draw_text(str(item['count']), 16, x + slot_size - 12, y + slot_size - 12, (255, 255, 255))
                elif item['type'] == 'GRENADE':
                    pygame.draw.circle(self.screen, COLOR_GRENADE, (x + slot_size//2, y + slot_size//2), 12)
                    self.draw_text(str(item['count']), 16, x + slot_size - 12, y + slot_size - 12, (255, 255, 255))
                elif item['type'] == 'CRYO':
                    pygame.draw.rect(self.screen, COLOR_CRYO_NODE, (x + 15, y + 15, slot_size-30, slot_size-30))
                    self.draw_text(str(item['count']), 16, x + slot_size - 12, y + slot_size - 12, (255, 255, 255))

    def draw_shop(self):
        self._draw_overlay_bg()
        panel_w, panel_h = 600, 500
        panel_x = (SCREEN_WIDTH - panel_w) // 2
        panel_y = (SCREEN_HEIGHT - panel_h) // 2
        
        pygame.draw.rect(self.screen, COLOR_UI_BG, (panel_x, panel_y, panel_w, panel_h))
        pygame.draw.rect(self.screen, COLOR_UI_BORDER, (panel_x, panel_y, panel_w, panel_h), 3)

        self.draw_text("CORE DEFENSE SHOP", 30, SCREEN_WIDTH//2, panel_y + 30, COLOR_TEXT)
        self.draw_text(f"CASH: ${self.money}", 20, SCREEN_WIDTH//2, panel_y + 60, (0, 255, 0))
        
        tabs = ["WEAPONS", "DEFENSE", "UTILITY"]
        tab_w = panel_w // 3
        for i, tab in enumerate(tabs):
            tx = panel_x + i * tab_w
            ty = panel_y + 80
            if self.draw_button(tab, tx, ty, tab_w, 30, active=(self.shop_tab == tab)):
                self.shop_tab = tab

        cx = panel_x + 30
        cy = panel_y + 140
        
        if self.shop_tab == "WEAPONS":
            for i, w_key in enumerate(["PISTOL", "RIFLE", "SHOTGUN"]):
                w_data = WEAPON_STATS[w_key]
                row_y = cy + i * 60
                
                is_unlocked = w_key in self.unlocked_weapons
                is_owned = w_key in self.purchased_weapons
                
                name_str = f"{w_data['name']}"
                if not is_unlocked: name_str += " [LOCKED]"
                elif is_owned: name_str += " [OWNED]"
                else: name_str += f" ${w_data['cost']}" if w_data['cost'] > 0 else " FREE"
                
                name_color = COLOR_OWNED if is_owned else (255, 255, 255)
                if not is_unlocked: name_color = COLOR_LOCKED
                
                self.draw_text(name_str, 18, cx + 100, row_y + 15, name_color)
                
                if is_unlocked:
                    btn_text = "EQUIP" if is_owned else "BUY"
                    if self.draw_button(f"SLOT 1", cx + 250, row_y, 100, 30):
                        self.buy_item("WEAPONS", w_key, w_data['cost'], target_slot=0)
                    if self.draw_button(f"SLOT 2", cx + 360, row_y, 100, 30):
                        self.buy_item("WEAPONS", w_key, w_data['cost'], target_slot=1)
            
            if self.draw_button("SWAP 1 <-> 2", SCREEN_WIDTH//2 - 75, cy + 200, 150, 40):
                self.swap_weapons()

        elif self.shop_tab == "DEFENSE":
            if self.draw_button("WALL x1 ($45)", SCREEN_WIDTH//2 - 100, cy, 200, 40): self.buy_item("DEFENSE", "WALL", 45)
            if self.draw_button("CRYO x1 ($120)", SCREEN_WIDTH//2 - 100, cy + 50, 200, 40): self.buy_item("DEFENSE", "CRYO", 120)
        
        elif self.shop_tab == "UTILITY":
            if self.draw_button("GRENADE x1 ($80)", SCREEN_WIDTH//2 - 100, cy, 200, 40): self.buy_item("UTILITY", "GRENADE", 80)
            if self.draw_button("REPAIR CORE ($200)", SCREEN_WIDTH//2 - 100, cy + 50, 200, 40): self.buy_item("UTILITY", "CORE", 200)
            if self.draw_button("HEAL SELF ($100)", SCREEN_WIDTH//2 - 100, cy + 100, 200, 40): self.buy_item("UTILITY", "HP", 100)

        inv_y = panel_y + panel_h - 90
        self.draw_text("CURRENT INVENTORY:", 16, SCREEN_WIDTH//2, inv_y - 20, (180, 180, 180))
        
        
        slot_size = 50
        gap = 10
        start_x = (SCREEN_WIDTH - (5 * slot_size + 4 * gap)) // 2
        
        for i in range(5):
            x = start_x + i * (slot_size + gap)
            rect = pygame.Rect(x, inv_y, slot_size, slot_size)
            pygame.draw.rect(self.screen, (20, 20, 30), rect)
            pygame.draw.rect(self.screen, (100, 100, 100), rect, 2)
            self.draw_text(str(i+1), 10, x + 8, inv_y + 8, (150, 150, 150))
            
            item = self.inventory[i]
            if item:
                if item['type'] == 'WEAPON':
                    w_name = item.get('name', 'PISTOL')
                    color = WEAPON_STATS.get(w_name, WEAPON_STATS['PISTOL'])['color']
                    pygame.draw.circle(self.screen, color, (x + slot_size//2, inv_y + slot_size//2), 8)
                    self.draw_text(w_name[:1], 14, x + slot_size//2, inv_y + slot_size//2, (0,0,0))
                elif item['type'] == 'WALL':
                    pygame.draw.rect(self.screen, COLOR_PLAYER_WALL, (x + 10, inv_y + 10, slot_size-20, slot_size-20))
                    self.draw_text(str(item['count']), 12, x + slot_size - 10, inv_y + slot_size - 10, (255, 255, 255))
                elif item['type'] == 'GRENADE':
                    pygame.draw.circle(self.screen, COLOR_GRENADE, (x + slot_size//2, inv_y + slot_size//2), 10)
                    self.draw_text(str(item['count']), 12, x + slot_size - 10, inv_y + slot_size - 10, (255, 255, 255))
                elif item['type'] == 'CRYO':
                    pygame.draw.rect(self.screen, COLOR_CRYO_NODE, (x + 10, inv_y + 10, slot_size-20, slot_size-20))
                    self.draw_text(str(item['count']), 12, x + slot_size - 10, inv_y + slot_size - 10, (255, 255, 255))

        self.draw_text("PRESS [B] OR [ESC] TO CLOSE", 16, SCREEN_WIDTH//2, panel_y + panel_h + 20, (150, 150, 150))

    def draw_text(self, text, size, x, y, color=COLOR_TEXT):
        f = pygame.font.SysFont("Consolas", size, bold=True)
        img = f.render(str(text), True, color)
        self.screen.blit(img, img.get_rect(center=(x, y)))

    def run(self):
        while True:
            self.handle_input()
            self.update()
            self.draw()
            self.clock.tick(FPS)

if __name__ == "__main__":
    SystemGuardian().run()