import math
import re


num_perlins_noises = 2 #количество ступеней шума перлина


def get_grid_offset(x, y, config):
    """
    Генерирует детерминированный сдвиг (Z, W) на базе 4D-карты.
    Входные оси — глобальные координаты X и Y, а результат — сдвиг по X и Y.
    Благодаря привязке к сетке координат, соседние проходы толстых линий
    будут смещаться в одну и ту же сторону, сохраняя геометрию.
    """
    freq = config.get("noise_frequency", 0.3)
    max_jitter = config.get("max_jitter", 0.09)

    # Матрица синусоид формирует стабильное непрерывное векторное поле сдвигов
    noise_z = (0.5 * math.sin(freq * x) +
               0.3 * math.sin(freq * y + 1.2) +
               0.2 * math.sin(freq * (x + y) * 0.7))

    noise_w = (0.5 * math.sin(freq * y + 5.5) +
               0.3 * math.sin(freq * x + 3.1) +
               0.2 * math.sin(freq * (x - y) * 1.1))

    return noise_z * max_jitter, noise_w * max_jitter

def apply_directional_bias(dx, dy, config):
    """Добавляет искажение в зависимости от направления движения."""
    if not config.get("use_directional_bias", False):
        return 0.0, 0.0
    if dx == 0 and dy == 0:
        return 0.0, 0.0

    angle = math.atan2(dy, dx)
    bias_factor = math.sin(angle) ** 2
    seed_noise = math.sin(angle * 10) * 0.5

    dir_factor = config.get("directional_factor", 0.06)
    shift_x = seed_noise * dir_factor * bias_factor
    shift_y = seed_noise * dir_factor * bias_factor * 1.3
    return shift_x, shift_y



def process_noise(input_file, output_file, config):
    segment_splitting(input_file, input_file + "_segments.gcode", config)
    print("segments")
    calculate_fade_normal(input_file + "_segments.gcode", input_file + "_segments_reversed.gcode", config)
    print("process_segments")
    calculate_fade_reverse(input_file + "_segments_reversed.gcode", output_file, config)
    print("process_segments reversed")


def calculate_fade_normal(input_file, output_file, config):
    """Добавляет строго ЛИНЕЙНЫЙ коэфф. затухания для шума Перлина."""
    x_re = re.compile(r"X\s*([0-9.-]+)", re.IGNORECASE)
    y_re = re.compile(r"Y\s*([0-9.-]+)", re.IGNORECASE)
    z_re = re.compile(r"Z\s*([0-9.-]+)", re.IGNORECASE)

    curr_x, curr_y, curr_z = 0.0, 0.0, 0.0

    # Храним текущее физическое значение коэффициентов
    curr_f1, curr_f2 = 0.0, 0.0

    fade_factor_1 = config.get("fade_factor_1", 5.5)  # Расстояние полного нарастания для f1 (мм)
    fade_factor_2 = config.get("fade_factor_2", 15.0)  # Расстояние полного нарастания для f2 (мм)

    fade1_pattern = r'\bfade1=([01])\b'
    fade2_pattern = r'\bfade2=([01])\b'

    fade1_remove_pattern = r'\s*\bfade1=\d+(?:\.\d+)?\b\s*'
    fade2_remove_pattern = r'\s*\bfade2=\d+(?:\.\d+)?\b\s*'

    with open(input_file, "r", encoding="utf-8") as infile, open(
            output_file, "w", encoding="utf-8"
    ) as outfile:

        for line in infile:
            stripped = line.strip()

            if stripped.startswith("G1") or stripped.startswith("G0"):
                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)
                z_match = z_re.search(stripped)
                f1_match = re.search(fade1_pattern, stripped)
                f2_match = re.search(fade2_pattern, stripped)

                target_x = float(x_match.group(1)) if x_match else curr_x
                target_y = float(y_match.group(1)) if y_match else curr_y
                target_z = float(z_match.group(1)) if z_match else curr_z

                dx = target_x - curr_x
                dy = target_y - curr_y
                dz = target_z - curr_z
                segment_length = math.hypot(dx, dy, dz)

                if f1_match:
                    fade1_target_mode = float(f1_match.group(1))
                    if fade1_target_mode == 0:
                        curr_f1 = 0.0
                    else:
                        # Строго линейный шаг: длина участка деленная на общую дистанцию разгона
                        linear_step_1 = segment_length / max(fade_factor_1, 0.01)
                        curr_f1 = min(curr_f1 + linear_step_1, 1.0)

                    stripped = re.subn(fade1_remove_pattern, ' ', stripped)[0]
                    stripped += f"; fade1={round(curr_f1, 3)}"

                if f2_match:
                    fade2_target_mode = float(f2_match.group(1))
                    if fade2_target_mode == 0:
                        curr_f2 = 0.0
                    else:
                        # Строго линейный шаг для второго коэффициента
                        linear_step_2 = segment_length / max(fade_factor_2, 0.01)
                        curr_f2 = min(curr_f2 + linear_step_2, 1.0)

                    stripped = re.subn(fade2_remove_pattern, ' ', stripped)[0]
                    stripped += f"; fade2={round(curr_f2, 3)} "

                curr_x, curr_y, curr_z = target_x, target_y, target_z

            outfile.write(stripped + "\n")


def calculate_fade_reverse(input_file, output_file, config):
    """Добавляет коэфф. затухания, рассчитываемый с конца файла к началу."""
    x_re = re.compile(r"X\s*([0-9.-]+)", re.IGNORECASE)
    y_re = re.compile(r"Y\s*([0-9.-]+)", re.IGNORECASE)
    z_re = re.compile(r"Z\s*([0-9.-]+)", re.IGNORECASE)

    # Изменяем паттерны: теперь они находят любые вещественные числа (например, 0.123 или 1.0)
    fade1_pattern = r'\bfade1=([0-9.]+)'
    fade2_pattern = r'\bfade2=([0-9.]+)'

    fade1_remove_pattern = r'\s*\bfade1=[0-9.]+\s*'
    fade2_remove_pattern = r'\s*\bfade2=[0-9.]+\s*'

    fade_factor_1 = config.get("fade_factor_1", 1.5)
    fade_factor_2 = config.get("fade_factor_2", 4.0)

    with open(input_file, "r", encoding="utf-8") as infile:
        lines = infile.readlines()

    # Сначала сделаем прямой проход, чтобы точно знать координаты КАЖДОЙ строки G-кода.
    # Это критически важно, чтобы при движении назад правильно считать длины сегментов.
    coords = []
    cx, cy, cz = 0.0, 0.0, 0.0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("G1") or stripped.startswith("G0"):
            x_m = x_re.search(stripped)
            y_m = y_re.search(stripped)
            z_m = z_re.search(stripped)
            if x_m: cx = float(x_m.group(1))
            if y_m: cy = float(y_m.group(1))
            if z_m: cz = float(z_m.group(1))
        coords.append((cx, cy, cz))

    out_file_data = []

    # Инициализируем реверсивные коэффициенты (в конце файла они равны 0, если там fade=0, или 1)
    curr_rf1, curr_rf2 = 1.0, 1.0

    # Идем с конца в начало
    for pos in range(len(lines) - 1, -1, -1):
        line = lines[pos]
        stripped = line.strip()

        if stripped.startswith("G1") or stripped.startswith("G0"):
            # Координаты текущей точки и координаты ПРЕДЫДУЩЕЙ по ходу печати (pos-1)
            curr_x, curr_y, curr_z = coords[pos]
            prev_x, prev_y, prev_z = coords[pos - 1] if pos > 0 else (0.0, 0.0, 0.0)

            # Длина сегмента между ними
            segment_length = math.hypot(curr_x - prev_x, curr_y - prev_y, curr_z - prev_z)

            f1_match = re.search(fade1_pattern, stripped)
            f2_match = re.search(fade2_pattern, stripped)

            if f1_match:
                # Читаем значение fade1, полученное после прямого прохода
                normal_f1 = float(f1_match.group(1))

                # Если в этой точке нормальный проход требует 0, сбрасываем и реверсивный
                if normal_f1 == 0:
                    curr_rf1 = 0.0
                else:
                    # Рассчитываем плавный спад коэффициента назад к нулю
                    coeff = min(1, segment_length / max(fade_factor_1, 0.01))
                    curr_rf1 = min(curr_rf1 + coeff, 1.0) if normal_f1 > 0 else 0.0

                # Итоговый коэффициент — это минимум между прямым и реверсивным проходом
                final_f1 = min(normal_f1, curr_rf1)

                stripped = re.sub(fade1_remove_pattern, ' ', stripped)
                stripped += f"; fade1={round(final_f1, 3)}"

            if f2_match:
                normal_f2 = float(f2_match.group(1))

                if normal_f2 == 0:
                    curr_rf2 = 0.0
                else:
                    coeff = min(1, segment_length / max(fade_factor_2, 0.01))
                    curr_rf2 = min(curr_rf2 + coeff, 1.0) if normal_f2 > 0 else 0.0

                final_f2 = min(normal_f2, curr_rf2)

                stripped = re.sub(fade2_remove_pattern, ' ', stripped)
                stripped += f"; fade2={round(final_f2, 3)}"

        out_file_data.append(stripped)

    # Записываем обратно в правильном (прямом) порядке
    with open(output_file, "w", encoding="utf-8") as outfile:
        for i in range(len(out_file_data) - 1, -1, -1):
            outfile.write(out_file_data[i] + "\n")


def segment_splitting(input_file, output_file, config):
    """
    Разбивает малые участки (< 10мм) на сегменты по 0.25мм,
    применяет к ним 4D карту смещений и сглаживает переходы на границах с длинными линиями.
    """
    x_re = re.compile(r"X\s*([0-9.-]+)", re.IGNORECASE)
    y_re = re.compile(r"Y\s*([0-9.-]+)", re.IGNORECASE)
    z_re = re.compile(r"Z\s*([0-9.-]+)", re.IGNORECASE)

    curr_x, curr_y, curr_z = 0.0, 0.0, 0.0

    # Флаг, указывающий, была ли предыдущая линия длинной (>= 10мм)
    prev_was_long = True

    with open(input_file, "r", encoding="utf-8") as infile, open(
            output_file, "w", encoding="utf-8"
    ) as outfile:

        for line in infile:
            stripped = line.strip()

            if stripped.startswith("G1"):
                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)
                z_match = z_re.search(stripped)

                if x_match or y_match:
                    target_x = float(x_match.group(1)) if x_match else curr_x
                    target_y = float(y_match.group(1)) if y_match else curr_y
                    target_z = float(z_match.group(1)) if z_match else curr_z

                    dx = target_x - curr_x
                    dy = target_y - curr_y
                    dz = target_z - curr_z
                    segment_length = math.hypot(dx, dy, dz)

                    # --- Вариант 1: Большое перемещение (>= 10 мм) ---
                    if segment_length >= 4.6 or segment_length == 0:
                        curr_x, curr_y, curr_z = target_x, target_y, target_z
                        prev_was_long = True
                        outfile.write(stripped + "; fade1=0 fade2=0" + "\n")
                        continue

                    # --- Вариант 2: Малое перемещение (< 10 мм) ---
                    step_size = 0.25
                    num_steps = max(1, math.ceil(segment_length / step_size))

                    sub_dx = dx / num_steps
                    sub_dy = dy / num_steps
                    sub_dz = dz / num_steps

                    # Проверяем, будет ли СЛЕДУЮЩАЯ линия длинной (смотрим наперед здесь нельзя,
                    # но мы можем плавно гасить шум к концу текущего отрезка, если бы знали.
                    # Для компенсации входа/выхода считаем расстояние до точек смены режима)

                    for step in range(1, num_steps + 1):
                        next_x = curr_x + sub_dx
                        next_y = curr_y + sub_dy
                        next_z = curr_z + sub_dz

                        # 1. Генерируем чистый сдвиг из глобальной 4D карты
                        '''total_shift_x, total_shift_y = 0.0, 0.0
                        if config.get("use_smooth_noise", True):
                            sx, sy = get_grid_offset(next_x, next_y, config)
                            total_shift_x += sx
                            total_shift_y += sy

                        # 2. Добавляем влияние направления линии
                        bx, by = apply_directional_bias(sub_dx, sub_dy, config)
                        total_shift_x += bx
                        total_shift_y += by

                        # 3. Рассчитываем плавный переход (blend_factor)
                        # Затухание на старте после длинной линии
                        dist_from_start = math.hypot(next_x - last_boundary_x, next_y - last_boundary_y)

                        # Затухание в конце перед приходом в финишную точку (если мы знаем, что выходим к длинной траектории)
                        # Так как мы уже внутри короткого сегмента, считаем расстояние до конца текущего малого отрезка
                        dist_to_end = math.hypot(target_x - next_x, target_y - next_y)

                        blend_factor = 1.0

                        # Если старт был от длинной линии — плавно разгоняем шум
                        if prev_was_long and dist_from_start < blend_zone:
                            blend_factor = min(blend_factor, dist_from_start / blend_zone)

                        # Коэффициент не может быть меньше 0
                        blend_factor = max(0.0, blend_factor)'''

                        # Применяем сглаженный сдвиг
                        final_x = round(next_x, 3)
                        final_y = round(next_y, 3)
                        final_z = round(next_z, 3)

                        # Обновляем текущие идеальные координаты
                        curr_x, curr_y, curr_z = next_x, next_y, next_z

                        # Собираем строку G-кода обратно
                        new_line = stripped
                        if x_match:
                            new_line = re.sub(r"X\s*[0-9.-]+", f"X{final_x}", new_line, flags=re.IGNORECASE)
                        if y_match:
                            new_line = re.sub(r"Y\s*[0-9.-]+", f"Y{final_y}", new_line, flags=re.IGNORECASE)
                        if z_match:
                            new_line = re.sub(r"Z\s*[0-9.-]+", f"Z{final_z}", new_line, flags=re.IGNORECASE)

                        # Если в исходной строке был только один компонент, добавляем второй,
                        # так как шум смещает инструмент в обе стороны одновременно
                        if x_match and not y_match:
                            new_line += f" Y{final_y}"
                        elif y_match and not x_match:
                            new_line += f" X{final_x}"

                        outfile.write(new_line + "; fade1=1 fade2=1" + "\n")

                    # После завершения цикла малых шагов фиксируем, что режим длинной линии отключен
                    prev_was_long = False
                    continue

            # Корректно отслеживаем координаты при холостом ходе G0
            if stripped.startswith("G0"):
                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)
                if x_match:
                    curr_x = float(x_match.group(1))
                if y_match:
                    curr_y = float(y_match.group(1))

                if prev_was_long:
                    stripped += "; fade1=0 fade2=0"
                else:
                    stripped += "; fade1=1 fade2=1"

            outfile.write(stripped + "\n")
