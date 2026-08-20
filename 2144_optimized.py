import io
import math
import random
import threading
from os import listdir
from os.path import isfile, join

import numpy as np
from tinytag import TinyTag
import pygame
import subprocess
import os
import mpv


# ===========================================================================
# SETUP
# ===========================================================================

pygame.init()

player = mpv.MPV(
    video=False,
    audio_device='auto'
)

SCREEN_WIDTH = 128
SCREEN_HEIGHT = 32

# UI refresh rate. This is a tiny 128x32 status-style display, not a game,
# so there's no benefit to redrawing at 60fps - it just burns CPU/power.
# 15fps is smooth enough for scrolling text / CD spin / progress bar.
TARGET_FPS = 15

screen = pygame.display.set_mode(
    (SCREEN_WIDTH, SCREEN_HEIGHT)
)

pygame.display.set_caption(
    "Music Player"
)

pygame.event.set_grab(True)

clock = pygame.time.Clock()

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

TRACK_CHANGED = pygame.USEREVENT + 1


# ===========================================================================
# TEXT RENDER CACHE
# ===========================================================================
#
# font.render() rasterizes glyphs from scratch every call. Most of the text
# we draw (album/song/artist names, labels, etc.) doesn't change from one
# frame to the next - only which row is selected does. Caching rendered
# surfaces keyed by (font, text, color) means we pay the rasterization cost
# once per distinct combination instead of every single frame.

_text_render_cache = {}


def render_text_cached(font, text, color):

    key = (id(font), text, color)

    surf = _text_render_cache.get(key)

    if surf is None:

        surf = font.render(text, True, color)
        _text_render_cache[key] = surf

    return surf


# ===========================================================================
# PLAYBACK STATE
# ===========================================================================

queue = []
queue_index = 0
current_tag = None
is_paused = False

queue_source_view = "songs"


# ===========================================================================
# SCREENSAVER
# ===========================================================================

SCREENSAVER_TIMEOUT = 60.0

idle_seconds = 0.0
screensaver_active = False
current_artwork_surface = None


# ===========================================================================
# MPV PLAYLIST POSITION
# ===========================================================================

def _on_playlist_pos_change(name, value):
    """
    MPV is authoritative about which item in its playlist is playing.

    We mirror MPV's playlist position into queue_index.
    """

    global queue_index

    if value is None or value < 0:
        return

    queue_index = int(value)

    scroll_states.clear()
    cd_angle_reset()

    pygame.event.post(
        pygame.event.Event(TRACK_CHANGED)
    )


player.observe_property(
    'playlist-pos',
    _on_playlist_pos_change
)


# ===========================================================================
# EQ BACKEND
# ===========================================================================

FREQUENCIES = [
    31,
    62,
    125,
    250,
    500,
    1000,
    2000,
    4000,
    8000,
    16000
]


def format_freq(freq):
    return (
        f"{freq / 1000:.0f} kHz"
        if freq >= 1000
        else f"{freq} Hz"
    )


class EQBackend:

    def __init__(self, freqs, mpv_player):
        self.player = mpv_player
        self._values = {
            freq: 50
            for freq in freqs
        }

    def get(self, freq):
        return self._values.get(
            freq,
            50
        )

    def set(self, freq, value):
        self._values[freq] = max(
            0,
            min(
                100,
                int(value)
            )
        )

        self._apply()

    def _apply(self):

        filters = []

        for freq in FREQUENCIES:

            gain_db = (
                (self._values[freq] - 50)
                / 50
                * 12
            )

            filters.append(
                f"equalizer="
                f"f={freq}:"
                f"width_type=o:"
                f"width=1:"
                f"g={gain_db:.2f}"
            )

        self.player.af = ",".join(
            filters
        )


eq_backend = EQBackend(
    FREQUENCIES,
    player
)


# ===========================================================================
# VOLUME
# ===========================================================================

VOLUME_STEP = 5


def adjust_volume(delta):

    current = player.volume or 0

    player.volume = max(
        0,
        min(
            100,
            current + delta
        )
    )


# ===========================================================================
# LIBRARY SCAN
# ===========================================================================
#
# Runs on a background thread so it overlaps with the startup splash
# instead of blocking before/after it. update_startup() below won't
# report "finished" until both the minimum splash duration has
# elapsed AND library_ready is set.

files = []

albums = {}
artists = {}
titles = {}
track_nums = {}

library_ready = threading.Event()

# albums/artists are populated once by scan_library() and never modified
# afterwards, so list(dict.keys()) always gives the same result. Rebuilding
# that list every keypress and every draw frame is wasted work - cache it
# and only rebuild if the underlying dict size actually changes.

_album_names_cache = []
_artist_names_cache = []


def get_album_names():

    global _album_names_cache

    if len(_album_names_cache) != len(albums):
        _album_names_cache = list(albums.keys())

    return _album_names_cache


def get_artist_names():

    global _artist_names_cache

    if len(_artist_names_cache) != len(artists):
        _artist_names_cache = list(artists.keys())

    return _artist_names_cache


def scan_library():

    scanned_files = [
        f
        for f in listdir("/mnt/vmshared/mu")
        if isfile(
            join("/mnt/vmshared/mu", f)
        )
    ]

    scanned_albums = {}
    scanned_artists = {}
    scanned_titles = {}
    scanned_track_nums = {}

    for filename in scanned_files:

        tag: TinyTag = TinyTag.get(
            "/mnt/vmshared/mu/" + filename
        )

        if tag.album not in scanned_albums:
            scanned_albums[tag.album] = []

        scanned_albums[tag.album].append(
            filename
        )

        if tag.artist not in scanned_artists:
            scanned_artists[tag.artist] = []

        scanned_artists[tag.artist].append(
            filename
        )

        scanned_titles[filename] = (
            tag.title
            if tag.title
            else filename
        )

        try:

            scanned_track_nums[filename] = (
                int(
                    str(tag.track).split("/")[0]
                )
                if tag.track
                else float("inf")
            )

        except ValueError:

            scanned_track_nums[filename] = float("inf")

    for album_name in scanned_albums:

        scanned_albums[album_name].sort(
            key=lambda f: scanned_track_nums[f]
        )

    for artist_name in scanned_artists:

        scanned_artists[artist_name].sort(
            key=lambda f: scanned_track_nums[f]
        )

    print(scanned_files)
    print(scanned_albums)
    print(scanned_artists)

    files.extend(scanned_files)
    albums.update(scanned_albums)
    artists.update(scanned_artists)
    titles.update(scanned_titles)
    track_nums.update(scanned_track_nums)

    library_ready.set()


library_scan_thread = threading.Thread(
    target=scan_library,
    daemon=True
)

library_scan_thread.start()


# ===========================================================================
# SHARED VIEW STATE
# ===========================================================================

view = "startup"


# ===========================================================================
# STARTUP / SPLASH
# ===========================================================================

DURATION_SECONDS = 4
BUBBLE_COUNT = 14

startup_font = pygame.font.SysFont(
    "Lower Pixel",
    12
)


class Bubble:

    def __init__(self):
        self.reset(start=True)

    def reset(self, start=False):

        self.x = (
            random.uniform(
                -10,
                SCREEN_WIDTH * 0.5
            )
            if start
            else random.uniform(-8, -2)
        )

        self.y = (
            random.uniform(
                SCREEN_HEIGHT * 0.3,
                SCREEN_HEIGHT + 8
            )
            if start
            else (
                SCREEN_HEIGHT
                + random.uniform(0, 6)
            )
        )

        self.radius = random.uniform(
            1.2,
            3.4
        )

        self.speed_y = random.uniform(
            6,
            14
        )

        self.speed_x = random.uniform(
            3,
            7
        )

        self.wobble_amp = random.uniform(
            0.6,
            1.8
        )

        self.wobble_speed = random.uniform(
            1.5,
            3.5
        )

        self.phase = random.uniform(
            0,
            math.tau
        )

        self.alpha = random.uniform(
            140,
            255
        )

    def update(self, dt, t):

        self.y -= (
            self.speed_y * dt
        )

        self.x += (
            self.speed_x * dt
            +
            math.sin(
                t * self.wobble_speed
                + self.phase
            )
            * self.wobble_amp
            * dt
        )

        if (
            self.y < -4
            or self.x > SCREEN_WIDTH + 4
        ):
            self.reset()


bubbles = [
    Bubble()
    for _ in range(BUBBLE_COUNT)
]

startup_t = 0.0


def draw_bubble(
    surf,
    x,
    y,
    radius,
    alpha
):

    r = max(
        1,
        round(radius)
    )

    size = r * 6

    layer = pygame.Surface(
        (size, size),
        pygame.SRCALPHA
    )

    cx = cy = size // 2

    for i in range(4, 0, -1):

        glow_r = r + i * 1.4
        glow_a = int(
            alpha * (0.10 / i)
        )

        pygame.draw.circle(
            layer,
            (
                140,
                210,
                255,
                glow_a
            ),
            (cx, cy),
            int(glow_r)
        )

    pygame.draw.circle(
        layer,
        (
            170,
            225,
            255,
            int(alpha * 0.35)
        ),
        (cx, cy),
        r
    )

    pygame.draw.circle(
        layer,
        (
            220,
            245,
            255,
            int(alpha * 0.9)
        ),
        (cx, cy),
        r,
        width=1
    )

    if r >= 2:

        hl_pos = (
            cx - max(1, r // 2),
            cy - max(1, r // 2)
        )

        pygame.draw.circle(
            layer,
            (
                255,
                255,
                255,
                int(alpha)
            ),
            hl_pos,
            max(1, r // 3)
        )

    surf.blit(
        layer,
        (
            x - size // 2,
            y - size // 2
        )
    )


def draw_startup_logo(
    surf,
    t
):

    text = render_text_cached(
        startup_font,
        "WELCOME BACK",
        WHITE
    )

    rect = text.get_rect(
        center=(
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2
        )
    )

    surf.blit(
        text,
        rect
    )


def update_startup(dt):

    global startup_t

    startup_t += dt

    screen.fill(BLACK)

    for bubble in bubbles:

        bubble.update(
            dt,
            startup_t
        )

        draw_bubble(
            screen,
            bubble.x,
            bubble.y,
            bubble.radius,
            bubble.alpha
        )

    draw_startup_logo(
        screen,
        startup_t
    )

    return (
        startup_t > DURATION_SECONDS
        and library_ready.is_set()
    )


# ===========================================================================
# BROWSER
# ===========================================================================

ROW_HEIGHT = 14

current_album = None
album_scroll = 0
album_selected = 0

song_scroll = 0
song_selected = 0

current_artist = None
artist_scroll = 0
artist_selected = 0

artist_song_scroll = 0
artist_song_selected = 0

list_font = pygame.font.SysFont(
    "Lower Pixel",
    10
)


def draw_list(
    surface,
    items,
    scroll_offset,
    selected_index,
    font,
    x=4,
    y=10,
    row_height=ROW_HEIGHT,
    display_func=str
):

    clip_rect = pygame.Rect(
        0,
        y,
        surface.get_width() - x,
        surface.get_height() - y
    )

    surface.set_clip(
        clip_rect
    )

    for i, item in enumerate(items):

        row_y = (
            y
            + i * row_height
            - scroll_offset
        )

        if (
            row_y + row_height < 0
            or row_y > surface.get_height()
        ):
            continue

        if i == selected_index:

            highlight_rect = pygame.Rect(
                x,
                row_y,
                surface.get_width() - x,
                row_height
            )

            pygame.draw.rect(
                surface,
                WHITE,
                highlight_rect
            )

            text_color = BLACK

        else:

            text_color = WHITE

        text_surf = render_text_cached(
            font,
            display_func(item),
            text_color
        )

        surface.blit(
            text_surf,
            (x, row_y)
        )

    surface.set_clip(None)


def scroll_to_selected(
    selected_index,
    scroll_offset,
    surface_height,
    y=10,
    row_height=ROW_HEIGHT
):

    visible_height = (
        surface_height - y
    )

    row_top = (
        selected_index
        * row_height
    )

    row_bottom = (
        row_top
        + row_height
    )

    if row_top < scroll_offset:

        scroll_offset = row_top

    elif (
        row_bottom
        > scroll_offset
        + visible_height
    ):

        scroll_offset = (
            row_bottom
            - visible_height
        )

    return scroll_offset


def max_scroll(
    item_count,
    surface_height,
    row_height=ROW_HEIGHT
):

    content_height = (
        item_count
        * row_height
    )

    return max(
        0,
        content_height
        - surface_height
    )


# ===========================================================================
# EQ VIEW
# ===========================================================================

EQ_STEP = 5
eq_selected = 0

eq_font = pygame.font.SysFont(
    "Lower Pixel",
    8
)

eq_font_small = pygame.font.SysFont(
    "Lower Pixel",
    7
)


def eq_adjust(delta):

    freq = FREQUENCIES[
        eq_selected
    ]

    current = eq_backend.get(
        freq
    )

    eq_backend.set(
        freq,
        current + delta
    )


def eq_reset_band():

    eq_backend.set(
        FREQUENCIES[eq_selected],
        50
    )


def draw_eq(surface):

    surface.fill(BLACK)

    freq = FREQUENCIES[
        eq_selected
    ]

    value = eq_backend.get(
        freq
    )

    header = f"{freq}  {value}"

    header_surf = render_text_cached(
        eq_font,
        header,
        WHITE
    )

    surface.blit(
        header_surf,
        (4, 2)
    )

    bar_x = 4
    bar_bottom = 28
    bar_top = 12

    bar_height = (
        bar_bottom - bar_top
    )

    filled_height = int(
        (value / 100)
        * bar_height
    )

    bar_rect = pygame.Rect(
        bar_x,
        bar_bottom - filled_height,
        6,
        filled_height
    )

    pygame.draw.rect(
        surface,
        WHITE,
        bar_rect
    )

    pygame.draw.rect(
        surface,
        WHITE,
        pygame.Rect(
            bar_x,
            bar_top,
            6,
            bar_height
        ),
        width=1
    )

    strip_x = 16

    strip_w = (
        SCREEN_WIDTH - strip_x
    ) / len(FREQUENCIES)

    for i, band in enumerate(
        FREQUENCIES
    ):

        value = eq_backend.get(
            band
        )

        col_x = int(
            strip_x
            + i * strip_w
        )

        col_w = max(
            1,
            int(strip_w) - 1
        )

        col_height = int(
            (value / 100)
            * bar_height
        )

        col_rect = pygame.Rect(
            col_x,
            bar_bottom - col_height,
            col_w,
            col_height
        )

        color = (
            WHITE
            if i == eq_selected
            else (110, 110, 110)
        )

        pygame.draw.rect(
            surface,
            color,
            col_rect
        )


# ===========================================================================
# PLAYING VIEW
# ===========================================================================

GRID = 16
PIXEL_SCALE = 1

SEEK_STEP = 10.0
HOLD_THRESHOLD = 0.35
SEEK_REPEAT_RATE = 0.15

right_held_time = 0.0
left_held_time = 0.0

right_is_holding = False
left_is_holding = False

seek_position = 0.0
position_baseline = 0.0

title_font = pygame.font.SysFont(
    "Lower Pixel",
    10
)

artist_font = pygame.font.SysFont(
    "Lower Pixel",
    8
)

info_font = pygame.font.SysFont(
    "Lower Pixel",
    7
)

title_rect = pygame.Rect(
    2,
    2,
    SCREEN_WIDTH - 30,
    10
)

artist_rect = pygame.Rect(
    2,
    12,
    SCREEN_WIDTH - 50,
    8
)

album_rect = pygame.Rect(
    2,
    22,
    SCREEN_WIDTH - 50,
    8
)

scroll_speed = 10
pause_time = 800

scroll_states = {}

cd_angle = 0
rotation_speed = 180


# ===========================================================================
# CD
# ===========================================================================

def build_cd_surface(
    grid,
    pixel_scale
):

    cx = cy = (
        grid - 1
    ) / 2

    radius = (
        grid / 2
        - 0.5
    )

    small = pygame.Surface(
        (grid, grid),
        pygame.SRCALPHA
    )

    for y in range(grid):

        for x in range(grid):

            dx = x - cx
            dy = y - cy

            dist = math.hypot(
                dx,
                dy
            )

            if dist > radius:
                continue

            a = dx + dy
            b = dx - dy

            band_width = 3.4
            hole_ring_r = 4.2
            hole_gap_r = 3.0

            in_streak_1 = (
                abs(a - 3.0)
                < band_width
                and b > hole_ring_r * 0.6
            )

            in_streak_2 = (
                abs(a + 3.0)
                < band_width
                and b < -hole_ring_r * 0.6
            )

            if dist < hole_gap_r:
                col = BLACK

            elif dist < hole_ring_r:
                col = WHITE

            elif (
                in_streak_1
                or in_streak_2
            ):
                col = BLACK

            else:
                col = WHITE

            small.set_at(
                (x, y),
                col
            )

    return pygame.transform.scale(
        small,
        (
            grid * pixel_scale,
            grid * pixel_scale
        )
    )


CD_SURFACE = build_cd_surface(
    GRID,
    PIXEL_SCALE
)

# pygame.transform.rotate() re-samples every pixel of the source image on
# every single call. Since the CD art itself never changes, we only need to
# do that resampling once per distinct angle. Precompute a fixed set of
# rotated frames up front and just pick the closest one each frame instead
# of rotating live.
CD_ANGLE_STEPS = 60
CD_ROTATED_FRAMES = [
    pygame.transform.rotate(
        CD_SURFACE,
        step * (360 / CD_ANGLE_STEPS)
    )
    for step in range(CD_ANGLE_STEPS)
]


def update_and_draw_cd(
    surf,
    dt,
    pos
):

    global cd_angle

    cd_angle = (
        cd_angle
        - rotation_speed * dt
    ) % 360

    frame_index = int(
        round(cd_angle / (360 / CD_ANGLE_STEPS))
    ) % CD_ANGLE_STEPS

    rotated_cd = CD_ROTATED_FRAMES[frame_index]

    rotated_rect = rotated_cd.get_rect(
        center=pos
    )

    surf.blit(
        rotated_cd,
        rotated_rect
    )


def cd_angle_reset():

    global cd_angle

    cd_angle = 0


# ===========================================================================
# SCROLLING TEXT
# ===========================================================================

def draw_scrolling_text(
    key,
    text,
    font,
    text_col,
    rect,
    dt_ms
):

    if key not in scroll_states:

        scroll_states[key] = {
            "scroll_x": 0,
            "scroll_dir": -1,
            "pause_timer": 0
        }

    state = scroll_states[key]

    text_surf = render_text_cached(
        font,
        text,
        text_col
    )

    text_w = text_surf.get_width()

    if text_w <= rect.width:

        screen.blit(
            text_surf,
            (rect.x, rect.y)
        )

        return

    max_offset = (
        text_w - rect.width
    )

    if state["pause_timer"] > 0:

        state["pause_timer"] -= dt_ms

    else:

        state["scroll_x"] += (
            state["scroll_dir"]
            * scroll_speed
            * (dt_ms / 1000)
        )

        if state["scroll_x"] <= 0:

            state["scroll_x"] = 0
            state["scroll_dir"] = 1
            state["pause_timer"] = pause_time

        elif (
            state["scroll_x"]
            >= max_offset
        ):

            state["scroll_x"] = max_offset
            state["scroll_dir"] = -1
            state["pause_timer"] = pause_time

    old_clip = screen.get_clip()

    screen.set_clip(rect)

    screen.blit(
        text_surf,
        (
            rect.x
            - state["scroll_x"],
            rect.y
        )
    )

    screen.set_clip(
        old_clip
    )


def draw_text(
    text,
    font,
    text_col,
    x,
    y
):

    img = render_text_cached(
        font,
        text,
        text_col
    )

    screen.blit(
        img,
        (x, y)
    )


# ===========================================================================
# CURRENT TAG
# ===========================================================================

def load_current_tag():

    global current_tag

    if (
        queue
        and
        0 <= queue_index < len(queue)
    ):

        current_tag = TinyTag.get(
            "/mnt/vmshared/mu/"
            + queue[queue_index],
            image=True
        )

    else:

        current_tag = None

    load_artwork()


# ===========================================================================
# ALBUM ARTWORK (MONOCHROME)
# ===========================================================================

MONO_THRESHOLD = 128
ARTWORK_SIZE = SCREEN_HEIGHT


def monochrome_cover_fit(
    source_surface,
    target_w,
    target_h
):
    """
    Scales source_surface to cover a target_w x target_h box
    (cropping the overflow), then thresholds every pixel to
    pure white or pure black.
    """

    src_w, src_h = source_surface.get_size()

    scale = max(
        target_w / src_w,
        target_h / src_h
    )

    scaled_w = max(1, round(src_w * scale))
    scaled_h = max(1, round(src_h * scale))

    scaled = pygame.transform.smoothscale(
        source_surface,
        (scaled_w, scaled_h)
    )

    crop_x = (scaled_w - target_w) // 2
    crop_y = (scaled_h - target_h) // 2

    cropped = scaled.subsurface(
        pygame.Rect(
            crop_x,
            crop_y,
            target_w,
            target_h
        )
    ).copy()

    # A per-pixel Python loop (via PixelArray) over even a 32x32 image is
    # ~1000 individual attribute lookups/branches done in pure Python. This
    # runs every time the track changes, which would otherwise cause a
    # visible stutter. numpy does the same threshold math in one vectorized
    # pass instead, with an identical result.
    rgb = pygame.surfarray.array3d(
        cropped
    ).astype(np.float32)

    luminance = (
        rgb[:, :, 0] * 0.299
        + rgb[:, :, 1] * 0.587
        + rgb[:, :, 2] * 0.114
    )

    is_white = luminance >= MONO_THRESHOLD

    mono = pygame.Surface((target_w, target_h))

    mono_pixels = pygame.surfarray.pixels3d(mono)
    mono_pixels[is_white] = WHITE
    mono_pixels[~is_white] = BLACK
    del mono_pixels

    return mono


def load_artwork():

    global current_artwork_surface

    current_artwork_surface = None

    if current_tag is None:
        return

    image = current_tag.images.any

    if image is None or not image.data:
        return

    try:

        raw_surface = pygame.image.load(
            io.BytesIO(image.data)
        ).convert()

    except (pygame.error, OSError):
        return

    current_artwork_surface = monochrome_cover_fit(
        raw_surface,
        ARTWORK_SIZE,
        ARTWORK_SIZE
    )


# ===========================================================================
# START PLAYING
# ===========================================================================

def start_playing(
    new_queue,
    start_index=0,
    source_view="songs"
):

    global queue
    global queue_index
    global view
    global scroll_states
    global cd_angle
    global seek_position
    global position_baseline
    global queue_source_view
    global is_paused

    if not new_queue:
        return

    # Make an independent copy.
    queue = list(
        new_queue
    )

    if not queue:
        return

    # Since the caller normally passes items[selected:],
    # selected song is index 0.
    start_index = max(
        0,
        min(
            int(start_index),
            len(queue) - 1
        )
    )

    queue_index = start_index

    scroll_states.clear()
    cd_angle = 0

    seek_position = 0.0
    position_baseline = 0.0

    queue_source_view = source_view
    is_paused = False

    # -----------------------------------------------------------------------
    # REBUILD MPV PLAYLIST
    #
    # The first file REPLACES the current playlist.
    # The remaining files are APPENDED.
    #
    # This preserves the MPV playlist for gapless playback.
    # -----------------------------------------------------------------------

    first_file = join(
        "/mnt/vmshared/mu",
        queue[start_index]
    )

    print()
    print("================================")
    print("START PLAYING")
    print("queue:", queue)
    print("queue_index:", queue_index)
    print("first file:", first_file)
    print("================================")

    player.command(
        "loadfile",
        first_file,
        "replace"
    )

    # Append everything after the selected track.
    for filename in queue[start_index + 1:]:

        player.command(
            "loadfile",
            join(
                "/mnt/vmshared/mu",
                filename
            ),
            "append"
        )

    load_current_tag()

    view = "playing"


# ===========================================================================
# JUMP TO TRACK
# ===========================================================================

def jump_to_track(
    new_index
):

    global seek_position
    global position_baseline
    global is_paused

    if not queue:
        return

    if not (
        0 <= new_index < len(queue)
    ):
        return

    scroll_states.clear()
    cd_angle_reset()

    seek_position = 0.0
    position_baseline = 0.0

    is_paused = False

    print()
    print("JUMP TO TRACK")
    print("queue:", queue)
    print("requested index:", new_index)
    print("requested file:", queue[new_index])

    # IMPORTANT:
    # Do not manually update queue_index here.
    #
    # MPV changes playlist position.
    # playlist-pos observer updates queue_index.
    player.command(
        "playlist-play-index",
        str(new_index)
    )


# ===========================================================================
# PAUSE
# ===========================================================================

def toggle_pause():

    global is_paused

    if not queue:
        return

    is_paused = not is_paused

    player.pause = is_paused


# ===========================================================================
# SEEK
# ===========================================================================

def seek_by(
    delta_seconds
):

    if (
        current_tag is None
        or current_tag.duration is None
    ):
        return

    player.command(
        "seek",
        str(delta_seconds),
        "relative"
    )


def track_position():

    return player.time_pos or 0.0


# ===========================================================================
# PROGRESS BAR
# ===========================================================================

def draw_progress_bar(
    x,
    y,
    width_chars,
    font
):

    if (
        current_tag is None
        or not current_tag.duration
    ):
        return

    pos = track_position()

    duration = current_tag.duration

    frac = max(
        0.0,
        min(
            1.0,
            pos / duration
        )
    )

    filled = int(
        round(
            frac * width_chars
        )
    )

    bar = (
        "#"
        * filled
        +
        "-"
        * (
            width_chars
            - filled
        )
    )

    draw_text(
        bar,
        font,
        WHITE,
        x,
        y
    )


# ===========================================================================
# PLAYING SCREEN
# ===========================================================================

def draw_playing(
    dt_sec,
    dt_ms
):

    screen.fill(BLACK)

    if (
        not queue
        or current_tag is None
    ):
        return

    update_and_draw_cd(
        screen,
        0.0 if is_paused else dt_sec,
        (118, 8)
    )

    draw_scrolling_text(
        "title",
        current_tag.title
        or "Unknown Title",
        title_font,
        WHITE,
        title_rect,
        dt_ms
    )

    draw_scrolling_text(
        "artist",
        current_tag.artist
        or "Unknown Artist",
        artist_font,
        WHITE,
        artist_rect,
        dt_ms
    )

    draw_scrolling_text(
        "album",
        current_tag.album
        or "Unknown Album",
        info_font,
        WHITE,
        album_rect,
        dt_ms
    )

    samplerate = (
        current_tag.samplerate / 1000
        if current_tag.samplerate
        else 0
    )

    draw_text(
        f"{current_tag.bitdepth}/{samplerate}kHz",
        info_font,
        WHITE,
        85,
        22
    )

    draw_text(
        (
            current_tag.mime_type[6:]
            if current_tag.mime_type
            else "Unknown Format"
        ),
        info_font,
        WHITE,
        85,
        12
    )

    if is_paused:

        draw_text(
            "||",
            info_font,
            WHITE,
            118,
            20
        )

    draw_progress_bar(
        2,
        30,
        16,
        info_font
    )


# ===========================================================================
# SCREENSAVER SCREEN
# ===========================================================================

def draw_screensaver():

    screen.fill(BLACK)

    if (
        current_artwork_surface is None
        or current_tag is None
        or not current_tag.duration
    ):
        return

    pos = track_position()

    frac = max(
        0.0,
        min(
            1.0,
            pos / current_tag.duration
        )
    )

    travel_range = (
        SCREEN_WIDTH
        - ARTWORK_SIZE
    )

    x = int(
        round(
            frac * travel_range
        )
    )

    screen.blit(
        current_artwork_surface,
        (x, 0)
    )


# ===========================================================================
# MAIN LOOP
# ===========================================================================
run = True

while run:

        dt_ms = clock.tick(TARGET_FPS)
        dt_sec = dt_ms / 1000

        # ===================================================================
        # EVENTS
        # ===================================================================

        for event in pygame.event.get():

            # ----------------------------------------------------------------
            # ACTIVITY / SCREENSAVER WAKE
            # ----------------------------------------------------------------

            if event.type in (
                pygame.KEYDOWN,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEWHEEL
            ):

                idle_seconds = 0.0

                if screensaver_active:

                    screensaver_active = False

                    # swallow the input that woke the screen up
                    continue

            # ----------------------------------------------------------------
            # QUIT
            # ----------------------------------------------------------------

            if event.type == pygame.QUIT:

                run = False

            # ----------------------------------------------------------------
            # TRACK CHANGED
            # ----------------------------------------------------------------

            elif event.type == TRACK_CHANGED:

                load_current_tag()

            # ----------------------------------------------------------------
            # MOUSE WHEEL
            # ----------------------------------------------------------------

            elif (
                event.type == pygame.MOUSEWHEEL
                and view in (
                    "albums",
                    "songs",
                    "artists",
                    "artist_songs"
                )
            ):

                if view == "albums":

                    album_scroll -= (
                        event.y
                        * ROW_HEIGHT
                    )

                    album_scroll = max(
                        0,
                        min(
                            album_scroll,
                            max_scroll(
                                len(albums),
                                SCREEN_HEIGHT
                            )
                        )
                    )

                elif view == "songs":

                    song_scroll -= (
                        event.y
                        * ROW_HEIGHT
                    )

                    song_scroll = max(
                        0,
                        min(
                            song_scroll,
                            max_scroll(
                                len(albums[current_album]),
                                SCREEN_HEIGHT
                            )
                        )
                    )

                elif view == "artists":

                    artist_scroll -= (
                        event.y
                        * ROW_HEIGHT
                    )

                    artist_scroll = max(
                        0,
                        min(
                            artist_scroll,
                            max_scroll(
                                len(artists),
                                SCREEN_HEIGHT
                            )
                        )
                    )

                elif view == "artist_songs":

                    artist_song_scroll -= (
                        event.y
                        * ROW_HEIGHT
                    )

                    artist_song_scroll = max(
                        0,
                        min(
                            artist_song_scroll,
                            max_scroll(
                                len(artists[current_artist]),
                                SCREEN_HEIGHT
                            )
                        )
                    )

            # =================================================================
            # KEY DOWN
            # =================================================================

            elif event.type == pygame.KEYDOWN:

                # ----------------------------------------------------------------
                # GLOBAL SHORTCUTS
                # ----------------------------------------------------------------

                if (
                    view != "startup"
                    and event.key == pygame.K_1
                ):

                    view = "albums"

                elif (
                    view != "startup"
                    and event.key == pygame.K_2
                ):

                    view = "artists"

                elif (
                    view != "startup"
                    and event.key == pygame.K_3
                ):

                    if queue:
                        view = "playing"

                elif (
                    view != "startup"
                    and event.key == pygame.K_4
                ):

                    view = "eq"

                elif event.key == pygame.K_r:

                    run = False

                elif event.key == pygame.K_t:

                    adjust_volume(-VOLUME_STEP)

                elif event.key == pygame.K_y:

                    adjust_volume(VOLUME_STEP)

                # =============================================================
                # ALBUMS
                # =============================================================

                elif view == "albums":

                    items = get_album_names()

                    if event.key == pygame.K_DOWN:

                        if items:

                            album_selected = min(
                                album_selected + 1,
                                len(items) - 1
                            )

                            album_scroll = (
                                scroll_to_selected(
                                    album_selected,
                                    album_scroll,
                                    SCREEN_HEIGHT
                                )
                            )

                    elif event.key == pygame.K_UP:

                        album_selected = max(
                            album_selected - 1,
                            0
                        )

                        album_scroll = (
                            scroll_to_selected(
                                album_selected,
                                album_scroll,
                                SCREEN_HEIGHT
                            )
                        )

                    elif (
                        event.key == pygame.K_RETURN
                        and items
                    ):

                        current_album = items[
                            album_selected
                        ]

                        view = "songs"

                        song_selected = 0
                        song_scroll = 0

                # =============================================================
                # SONGS
                # =============================================================

                elif view == "songs":

                    items = albums[
                        current_album
                    ]

                    if event.key == pygame.K_DOWN:

                        song_selected = min(
                            song_selected + 1,
                            len(items) - 1
                        )

                        song_scroll = (
                            scroll_to_selected(
                                song_selected,
                                song_scroll,
                                SCREEN_HEIGHT
                            )
                        )

                    elif event.key == pygame.K_UP:

                        song_selected = max(
                            song_selected - 1,
                            0
                        )

                        song_scroll = (
                            scroll_to_selected(
                                song_selected,
                                song_scroll,
                                SCREEN_HEIGHT
                            )
                        )

                    elif (
                        event.key == pygame.K_RETURN
                        and items
                    ):

                        start_playing(
                            items[song_selected:],
                            start_index=0,
                            source_view="songs"
                        )

                    elif event.key in (
                        pygame.K_BACKSPACE,
                        pygame.K_ESCAPE
                    ):

                        view = "albums"
                        current_album = None

                # =============================================================
                # ARTISTS
                # =============================================================

                elif view == "artists":

                    items = get_artist_names()

                    if event.key == pygame.K_DOWN:

                        if items:

                            artist_selected = min(
                                artist_selected + 1,
                                len(items) - 1
                            )

                            artist_scroll = (
                                scroll_to_selected(
                                    artist_selected,
                                    artist_scroll,
                                    SCREEN_HEIGHT
                                )
                            )

                    elif event.key == pygame.K_UP:

                        artist_selected = max(
                            artist_selected - 1,
                            0
                        )

                        artist_scroll = (
                            scroll_to_selected(
                                artist_selected,
                                artist_scroll,
                                SCREEN_HEIGHT
                            )
                        )

                    elif (
                        event.key == pygame.K_RETURN
                        and items
                    ):

                        current_artist = items[
                            artist_selected
                        ]

                        view = "artist_songs"

                        artist_song_selected = 0
                        artist_song_scroll = 0

                # =============================================================
                # ARTIST SONGS
                # =============================================================

                elif view == "artist_songs":

                    items = artists[
                        current_artist
                    ]

                    if event.key == pygame.K_DOWN:

                        artist_song_selected = min(
                            artist_song_selected + 1,
                            len(items) - 1
                        )

                        artist_song_scroll = (
                            scroll_to_selected(
                                artist_song_selected,
                                artist_song_scroll,
                                SCREEN_HEIGHT
                            )
                        )

                    elif event.key == pygame.K_UP:

                        artist_song_selected = max(
                            artist_song_selected - 1,
                            0
                        )

                        artist_song_scroll = (
                            scroll_to_selected(
                                artist_song_selected,
                                artist_song_scroll,
                                SCREEN_HEIGHT
                            )
                        )

                    elif (
                        event.key == pygame.K_RETURN
                        and items
                    ):

                        start_playing(
                            items[artist_song_selected:],
                            start_index=0,
                            source_view="artist_songs"
                        )

                    elif event.key in (
                        pygame.K_BACKSPACE,
                        pygame.K_ESCAPE
                    ):

                        view = "artists"
                        current_artist = None

                # =============================================================
                # EQ
                # =============================================================

                elif view == "eq":

                    if event.key == pygame.K_RIGHT:

                        eq_selected = min(
                            eq_selected + 1,
                            len(FREQUENCIES) - 1
                        )

                    elif event.key == pygame.K_LEFT:

                        eq_selected = max(
                            eq_selected - 1,
                            0
                        )

                    elif event.key == pygame.K_UP:

                        eq_adjust(
                            EQ_STEP
                        )

                    elif event.key == pygame.K_DOWN:

                        eq_adjust(
                            -EQ_STEP
                        )

                    elif event.key == pygame.K_RETURN:

                        eq_reset_band()

                    elif event.key in (
                        pygame.K_BACKSPACE,
                        pygame.K_ESCAPE
                    ):

                        view = "albums"

                # =============================================================
                # PLAYING
                # =============================================================

                elif view == "playing":

                    if event.key in (
                        pygame.K_BACKSPACE,
                        pygame.K_ESCAPE
                    ):

                        view = queue_source_view

                    elif event.key == pygame.K_SPACE:

                        toggle_pause()

                    elif event.key == pygame.K_RIGHT:

                        right_is_holding = True
                        right_held_time = 0.0

                    elif event.key == pygame.K_LEFT:

                        left_is_holding = True
                        left_held_time = 0.0

            # =================================================================
            # KEY UP
            # =================================================================

            elif event.type == pygame.KEYUP:

                if view == "playing":

                    if event.key == pygame.K_RIGHT:

                        if (
                            right_is_holding
                            and
                            right_held_time
                            < HOLD_THRESHOLD
                        ):

                            jump_to_track(
                                queue_index + 1
                            )

                        right_is_holding = False
                        right_held_time = 0.0

                    elif event.key == pygame.K_LEFT:

                        if (
                            left_is_holding
                            and
                            left_held_time
                            < HOLD_THRESHOLD
                        ):

                            jump_to_track(
                                queue_index - 1
                            )

                        left_is_holding = False
                        left_held_time = 0.0

        # ===================================================================
        # IDLE / SCREENSAVER TIMEOUT
        # ===================================================================

        idle_seconds += dt_sec

        if (
            not screensaver_active
            and idle_seconds >= SCREENSAVER_TIMEOUT
        ):
            screensaver_active = True

        # ===================================================================
        # CONTINUOUS SEEK
        # ===================================================================

        if view == "playing":

            if right_is_holding:

                prev_time = right_held_time

                right_held_time += dt_sec

                if (
                    right_held_time
                    >= HOLD_THRESHOLD
                ):

                    if (
                        prev_time
                        < HOLD_THRESHOLD
                        or
                        int(
                            prev_time
                            / SEEK_REPEAT_RATE
                        )
                        !=
                        int(
                            right_held_time
                            / SEEK_REPEAT_RATE
                        )
                    ):

                        seek_by(
                            SEEK_STEP
                        )

            if left_is_holding:

                prev_time = left_held_time

                left_held_time += dt_sec

                if (
                    left_held_time
                    >= HOLD_THRESHOLD
                ):

                    if (
                        prev_time
                        < HOLD_THRESHOLD
                        or
                        int(
                            prev_time
                            / SEEK_REPEAT_RATE
                        )
                        !=
                        int(
                            left_held_time
                            / SEEK_REPEAT_RATE
                        )
                    ):

                        seek_by(
                            -SEEK_STEP
                        )

        # ===================================================================
        # DRAW
        # ===================================================================

        if screensaver_active:

            draw_screensaver()

        elif view == "startup":

            if update_startup(
                dt_sec
            ):

                view = "albums"

        elif view == "albums":

            screen.fill(BLACK)

            draw_list(
                screen,
                get_album_names(),
                album_scroll,
                album_selected,
                list_font,
                y=2
            )

        elif view == "songs":

            screen.fill(BLACK)

            draw_list(
                screen,
                albums[current_album],
                song_scroll,
                song_selected,
                list_font,
                y=2,
                display_func=lambda f: titles[f]
            )

        elif view == "artists":

            screen.fill(BLACK)

            draw_list(
                screen,
                get_artist_names(),
                artist_scroll,
                artist_selected,
                list_font,
                y=2
            )

        elif view == "artist_songs":

            screen.fill(BLACK)

            draw_list(
                screen,
                artists[current_artist],
                artist_song_scroll,
                artist_song_selected,
                list_font,
                y=2,
                display_func=lambda f: titles[f]
            )

        elif view == "eq":

            draw_eq(screen)

        elif view == "playing":

            draw_playing(
                dt_sec,
                dt_ms
            )

        pygame.display.flip()


pygame.quit()