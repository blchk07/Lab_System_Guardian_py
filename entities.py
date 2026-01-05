import pygame
import random
import math
from settings import *
from sprites import Bullet, Particle

class GridEntity(pygame.sprite.Sprite):
    def __init__(self, gx, gy, color):
        super().__init__()
        self.grid_pos = pygame.Vector2(gx, gy)
        self.pixel_pos = pygame.Vector2(gx * TILE_SIZE, gy * TILE_SIZE)
        self.target_pixel_pos = pygame.Vector2(self.pixel_pos)
        self.is_moving = False
        self.anim_speed = 0.2
        self.image = pygame.Surface((TILE_SIZE-4, TILE_SIZE-4), pygame.SRCALPHA)
        self.rect = self.image.get_rect(topleft=self.pixel_pos)
        self.hp = 100
        self.max_hp = 100
        self.color = color

    def move_to(self, dx, dy, game):
        if self.is_moving: return False
        new_gx, new_gy = self.grid_pos.x + dx, self.grid_pos.y + dy
        if 0 <= new_gx < game.map_size and 0 <= new_gy < game.map_size:
            if not game.is_tile_blocked(int(new_gx), int(new_gy)):
                self.grid_pos = pygame.Vector2(new_gx, new_gy)
                self.target_pixel_pos = pygame.Vector2(new_gx * TILE_SIZE, new_gy * TILE_SIZE)
                self.is_moving = True
                return True
        return False

    def update_animation(self):
        if self.is_moving:
            diff = self.target_pixel_pos - self.pixel_pos
            if diff.length() < 2:
                self.pixel_pos = pygame.Vector2(self.target_pixel_pos)
                self.is_moving = False
            else:
                self.pixel_pos += diff * self.anim_speed
        self.rect.topleft = self.pixel_pos

    def draw_hp_bar(self, surface, camera):
        if self.hp < self.max_hp:
            bar_w = TILE_SIZE - 8
            hp_w = bar_w * (max(0, self.hp) / self.max_hp)
            pygame.draw.rect(surface, (50, 50, 50), camera.apply_rect(pygame.Rect(self.rect.x + 4, self.rect.y - 10, bar_w, 6)))
            pygame.draw.rect(surface, (0, 255, 100), camera.apply_rect(pygame.Rect(self.rect.x + 4, self.rect.y - 10, hp_w, 6)))

class Player(GridEntity):
    def __init__(self, gx, gy):
        super().__init__(gx, gy, COLOR_PLAYER)
        pygame.draw.rect(self.image, self.color, (0, 0, TILE_SIZE-4, TILE_SIZE-4), border_radius=8)
        self.hp = 200
        self.max_hp = 200
        self.last_move_time = 0
        self.move_delay = 130

class Enemy(GridEntity):
    def __init__(self, gx, gy, wave_stats, color=COLOR_ENEMY):
        super().__init__(gx, gy, color)
        pygame.draw.polygon(self.image, self.color, [(TILE_SIZE//2, 4), (TILE_SIZE-6, TILE_SIZE-6), (6, TILE_SIZE-6)])
        self.hp = wave_stats['hp']
        self.max_hp = self.hp
        self.damage = wave_stats['damage']
        self.base_move_cooldown = wave_stats['speed']
        self.move_cooldown = self.base_move_cooldown
        self.last_move = pygame.time.get_ticks() + random.randint(0, 400)
        self.reward = 15
        self.is_slowed = False

    def check_slow(self, game):
        self.is_slowed = False
        for cryo in game.cryo_nodes:
            dist = abs(self.grid_pos.x - cryo.grid_pos.x) + abs(self.grid_pos.y - cryo.grid_pos.y)
            if dist <= cryo.radius:
                self.is_slowed = True
                break
        
        if self.is_slowed:
            self.move_cooldown = self.base_move_cooldown * 1.6
        else:
            self.move_cooldown = self.base_move_cooldown

    def draw_hp_bar(self, surface, camera):
        super().draw_hp_bar(surface, camera)
        if self.is_slowed:
             center = camera.apply_rect(self.rect).center
             pygame.draw.circle(surface, (0, 255, 255), (center[0], center[1] - 15), 4)

    def ai_logic(self, player_gx, player_gy, heatmap, game):
        self.check_slow(game)
        
        now = pygame.time.get_ticks()
        if not self.is_moving and now - self.last_move > self.move_cooldown:
            dist_to_player = abs(self.grid_pos.x - player_gx) + abs(self.grid_pos.y - player_gy)
            dist_to_core = heatmap.get((int(self.grid_pos.x), int(self.grid_pos.y)), 9999)
            
            dx, dy = 0, 0
            if dist_to_player < 7 and dist_to_player < (dist_to_core / 2):
                if player_gx > self.grid_pos.x: dx = 1
                elif player_gx < self.grid_pos.x: dx = -1
                elif player_gy > self.grid_pos.y: dy = 1
                elif player_gy < self.grid_pos.y: dy = -1
            else:
                curr_val = heatmap.get((int(self.grid_pos.x), int(self.grid_pos.y)), 9999)
                for move in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, ny = int(self.grid_pos.x + move[0]), int(self.grid_pos.y + move[1])
                    if heatmap.get((nx, ny), 9999) < curr_val:
                        dx, dy = move
                        break
            
            if dx != 0 or dy != 0:
                nx, ny = int(self.grid_pos.x + dx), int(self.grid_pos.y + dy)
                target_wall = game.get_player_wall_at(nx, ny)
                target_cryo = game.get_cryo_at(nx, ny)
                
                target = target_wall if target_wall else target_cryo
                
                if target:
                    target.hp -= self.damage * 2
                    if game.settings_particles:
                        col = COLOR_PLAYER_WALL if target_wall else COLOR_CRYO_NODE
                        game.particles.append(Particle(target.rect.centerx, target.rect.centery, col))
                else:
                    self.move_to(dx, dy, game)
            self.last_move = now

class ShooterEnemy(Enemy):
    def __init__(self, gx, gy, wave_stats):
        super().__init__(gx, gy, wave_stats, color=COLOR_ENEMY_RANGED)
        self.last_shot = 0
        self.shoot_delay = 1900
        self.reward = 40
        self.has_los = False

    def has_line_of_sight(self, target_pos, game):
        start = self.rect.center
        end = target_pos
        dist = math.hypot(end[0] - start[0], end[1] - start[1])
        if dist == 0: return True
        steps = int(dist / (TILE_SIZE / 2)) 
        for i in range(1, steps):
            t = i / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            gx, gy = int(x // TILE_SIZE), int(y // TILE_SIZE)
            if game.is_tile_blocked(gx, gy):
                return False
        return True

    def ai_logic(self, player_gx, player_gy, heatmap, game):
        self.check_slow(game)
        
        now = pygame.time.get_ticks()
        dist_to_player = abs(self.grid_pos.x - player_gx) + abs(self.grid_pos.y - player_gy)
        
        if dist_to_player < 8:
            self.has_los = self.has_line_of_sight(game.player.rect.center, game)
        else:
            self.has_los = False

        if now - self.last_shot > self.shoot_delay and dist_to_player < 8:
            if self.has_los:
                return 
            else:
                super().ai_logic(player_gx, player_gy, heatmap, game)
                return
        super().ai_logic(player_gx, player_gy, heatmap, game)

    def try_shoot(self, player_pos):
        if not self.has_los: return None
        
        now = pygame.time.get_ticks()
        delay = self.shoot_delay * (1.3 if self.is_slowed else 1.0)
        
        if now - self.last_shot > delay:
            self.last_shot = now
            angle = math.atan2(player_pos.y - self.rect.centery, player_pos.x - self.rect.centerx)
            return Bullet(self.rect.centerx, self.rect.centery, angle, is_enemy=True)
        return None

class ScoutEnemy(Enemy):
    def __init__(self, gx, gy, wave_stats):
        super().__init__(gx, gy, wave_stats, color=COLOR_SCOUT)
        self.hp = 35
        self.max_hp = 35
        self.move_cooldown = 450
        self.damage = 2.5
        self.reward = 10

class Bullet:
    def __init__(self, x, y, angle, is_enemy=False, damage=10, speed=13.5, max_dist=1000, color=COLOR_BULLET):
        self.start_pos = pygame.Vector2(x, y)
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
        self.active = True
        self.is_enemy = is_enemy
        self.damage = damage
        self.max_dist = max_dist
        self.rect = pygame.Rect(x-4, y-4, 8, 8)
        self.color = color

    def update(self, walls):
        self.pos += self.vel
        self.rect.center = (int(self.pos.x), int(self.pos.y))
        
        if self.pos.distance_to(self.start_pos) > self.max_dist:
            self.active = False
            return

        gx, gy = int(self.pos.x // TILE_SIZE), int(self.pos.y // TILE_SIZE)
        if (gx, gy) in walls: self.active = False
        if not (0 <= self.pos.x < 4000 and 0 <= self.pos.y < 4000): self.active = False

class Grenade:
    def __init__(self, start_x, start_y, target_x, target_y):
        self.pos = pygame.Vector2(start_x, start_y)
        self.target = pygame.Vector2(target_x, target_y)
        self.speed = 9.0
        self.active = True
        self.exploded = False
        self.blast_radius = 160
        self.damage = 180
        direction = self.target - self.pos
        if direction.length() > 0:
            self.vel = direction.normalize() * self.speed
        else:
            self.vel = pygame.Vector2(0, 0)

    def update(self):
        dist = self.pos.distance_to(self.target)
        if dist < self.speed:
            self.pos = self.target
            self.exploded = True
            return True 
        self.pos += self.vel
        return False

class BonusItem(pygame.sprite.Sprite):
    def __init__(self, gx, gy, type):
        super().__init__()
        self.grid_pos = pygame.Vector2(gx, gy)
        self.rect = pygame.Rect(gx * TILE_SIZE + 10, gy * TILE_SIZE + 10, 28, 28)
        self.image = pygame.Surface((28, 28), pygame.SRCALPHA)
        self.type = type
        self.draw_icon()

    def draw_icon(self):
        if self.type == "HEALTH":
            pygame.draw.rect(self.image, COLOR_BONUS_HP, (0, 0, 28, 28), border_radius=4)
            pygame.draw.rect(self.image, (255,255,255), (11, 4, 6, 20))
            pygame.draw.rect(self.image, (255,255,255), (4, 11, 20, 6))
        elif self.type == "CORE_REPAIR":
            pygame.draw.rect(self.image, COLOR_BONUS_CORE, (0, 0, 28, 28), border_radius=4)
            pygame.draw.circle(self.image, (255,255,255), (14, 14), 8)
        elif self.type == "GRENADE_BOX":
            pygame.draw.rect(self.image, COLOR_GRENADE_BONUS, (0, 0, 28, 28), border_radius=4)
            pygame.draw.circle(self.image, (50, 50, 50), (14, 14), 6)
        elif self.type == "WEAPON_CRATE":
            pygame.draw.rect(self.image, COLOR_WEAPON_CRATE, (0, 0, 28, 28), border_radius=4)
            pygame.draw.line(self.image, (0,0,0), (0,0), (28,28), 2)
            pygame.draw.line(self.image, (0,0,0), (28,0), (0,28), 2)
        elif self.type.startswith("BUFF_"):
            pygame.draw.circle(self.image, COLOR_BUFF, (14, 14), 14)
            font = pygame.font.SysFont("Consolas", 14, bold=True)
            t = self.type.split("_")[1][0]
            txt = font.render(t, True, (255, 255, 255))
            self.image.blit(txt, txt.get_rect(center=(14, 14)))


class EnemySpawner(GridEntity):
    def __init__(self, gx, gy):
        super().__init__(gx, gy, COLOR_SPAWNER)
        self.hp = 350
        self.max_hp = 350
        self.last_spawn = pygame.time.get_ticks()
        self.spawn_delay = 5500
        self.scouts_produced = 0
        self.max_scouts = 8
        self.reward = 150
        self._redraw()

    def _redraw(self):
        self.image.fill((0, 0, 0, 0))
        pygame.draw.rect(self.image, self.color, (2, 2, TILE_SIZE-8, TILE_SIZE-8), border_radius=6)
        if self.scouts_produced < self.max_scouts:
            pygame.draw.circle(self.image, (255, 255, 255), (TILE_SIZE//2-2, TILE_SIZE//2-2), TILE_SIZE//4)

    def get_adjacent_free_tile(self, game):
        neighbors = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        random.shuffle(neighbors)
        for dx, dy in neighbors:
            nx, ny = int(self.grid_pos.x + dx), int(self.grid_pos.y + dy)
            if 0 <= nx < game.map_size and 0 <= ny < game.map_size:
                if not game.is_tile_blocked(nx, ny):
                    return nx, ny
        return None

class EnergyNode(GridEntity):
    def __init__(self, gx, gy):
        super().__init__(gx, gy, COLOR_NODE)
        pygame.draw.circle(self.image, self.color, (TILE_SIZE//2-2, TILE_SIZE//2-2), TILE_SIZE//3)
        self.hp = 250
        self.max_hp = 250
        self.reward = 70

class PlayerWall(GridEntity):
    def __init__(self, gx, gy):
        super().__init__(gx, gy, COLOR_PLAYER_WALL)
        pygame.draw.rect(self.image, self.color, (0, 0, TILE_SIZE-4, TILE_SIZE-4), border_radius=4)
        self.hp = 250
        self.max_hp = 250
        self.spawn_time = pygame.time.get_ticks()
        self.lifetime = 60000

class CryoNode(GridEntity):
    def __init__(self, gx, gy):
        super().__init__(gx, gy, COLOR_CRYO_NODE)
        pygame.draw.rect(self.image, self.color, (4, 4, TILE_SIZE-8, TILE_SIZE-8), border_radius=4)
        pygame.draw.circle(self.image, (200, 240, 255), (TILE_SIZE//2-2, TILE_SIZE//2-2), 8)
        self.hp = 150
        self.max_hp = 150
        self.radius = 2
        self.spawn_time = pygame.time.get_ticks()
        self.lifetime = 60000

    def draw_range(self, surface, camera):
        radius_px = (self.radius * TILE_SIZE) + (TILE_SIZE // 2)
        center = camera.apply_rect(self.rect).center
        s = pygame.Surface((radius_px*2, radius_px*2), pygame.SRCALPHA)
        pygame.draw.circle(s, COLOR_CRYO_ZONE, (radius_px, radius_px), radius_px)
        surface.blit(s, (center[0] - radius_px, center[1] - radius_px))