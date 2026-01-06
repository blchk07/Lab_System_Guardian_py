import pygame
import random
import math
from settings import *

class Particle:
    base_surface = pygame.Surface((PARTICLE_SIZE, PARTICLE_SIZE))
    def __init__(self, x, y, color, speed_mult=1.0, decay_speed=None):
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2(random.uniform(-4, 4), random.uniform(-4, 4)) * speed_mult
        self.life = 255
        self.color = color
        self.decay = decay_speed if decay_speed else random.randint(10, 20)

    def update(self):
        self.pos += self.vel
        self.life -= self.decay
        return self.life > 0

    def draw(self, surface, camera):
        self.base_surface.set_alpha(max(0, self.life))
        self.base_surface.fill(self.color)
        surface.blit(self.base_surface, camera.apply_rect(pygame.Rect(self.pos.x, self.pos.y, PARTICLE_SIZE, PARTICLE_SIZE)))

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