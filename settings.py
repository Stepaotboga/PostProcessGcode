import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# Шум почерка (бывший DEFAULT_CONST, без параметров смещения)
NOISE_CONST = {
    "tremor_freq": 1.14,     # частота микро-дрожи
    "tremor_amp": 0.18,      # амплитуда микро-дрожи, мм
    "height_freq": 0.09,     # частота ухода высоты букв
    "height_amp": 0.41,      # амплитуда ухода высоты, мм
    "fade_factor_1": 5.2,    # дистанция нарастания fade1, мм
    "fade_factor_2": 12.1,   # дистанция нарастания fade2, мм
}

# Z-offset и паузы (стирание карандаша)
OFFSET_CONST = {
    "pause_dist": 5000.0,    # дистанция до паузы, мм
    "defa_s": 0.75,          # выдвижение карандаша S, мм
    "defa_l": 0.05,          # стандартный z_offset l, мм
}

# Предпросмотр
VIEW_CONST = {
    "pen_width_mm": 0.45,    # толщина линии карандаша
    "bed_x": 400.0,          # рабочая область, мм
    "bed_y": 435.0,
    "pen_down_z": 1.0,       # Z ниже этого значения = карандаш на бумаге
    "simplify_eps": 0.03,    # допуск прореживания точек (Рамер-Дуглас-Пекер), мм
    "view_margin": 50.0,     # запас за границами стола при панорамировании, мм
    "view_padding": 0.03,    # отступ при начальном показе
    "grid_major": 50,        # крупная сетка, мм
    "grid_minor": 10,        # мелкая сетка, мм
}

SECTIONS = {"noise": NOISE_CONST, "offset": OFFSET_CONST, "view": VIEW_CONST}


def _read_file():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_section(name):
    """Значения из settings.py, поверх них то, что сохранено в settings.json."""
    values = dict(SECTIONS[name])
    saved = _read_file().get(name, {})
    for key in values:                      # берём только известные ключи
        if key in saved:
            values[key] = saved[key]
    return values


def save_section(name, values):
    data = _read_file()
    data[name] = {k: values[k] for k in SECTIONS[name]}
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)