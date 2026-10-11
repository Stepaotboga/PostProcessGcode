import math
import re


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
    """
    Разбивает малые участки (< 10мм) на сегменты по 0.25мм,
    применяет к ним 4D карту смещений и сглаживает переходы на границах с длинными линиями.
    """
    x_re = re.compile(r"X\s*([0-9.-]+)", re.IGNORECASE)
    y_re = re.compile(r"Y\s*([0-9.-]+)", re.IGNORECASE)

    curr_x, curr_y = 0.0, 0.0

    # Параметры зоны плавного перехода (в миллиметрах)
    blend_zone = 3.0

    # Флаг, указывающий, была ли предыдущая линия длинной (>= 10мм) или холостым ходом G0
    prev_was_long_or_g0 = True
    # Координаты последней точки стыка с длинной линией / G0
    last_boundary_x, last_boundary_y = 0.0, 0.0

    with open(input_file, "r", encoding="utf-8") as infile, open(
            output_file, "w", encoding="utf-8"
    ) as outfile:

        for line in infile:
            stripped = line.strip()

            if stripped.startswith("G1"):
                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)

                if x_match or y_match:
                    target_x = float(x_match.group(1)) if x_match else curr_x
                    target_y = float(y_match.group(1)) if y_match else curr_y

                    dx = target_x - curr_x
                    dy = target_y - curr_y
                    segment_length = math.hypot(dx, dy)

                    # --- Вариант 1: Большое перемещение (>= 10 мм) ---
                    if segment_length >= 10.0 or segment_length == 0:
                        curr_x, curr_y = target_x, target_y
                        last_boundary_x, last_boundary_y = curr_x, curr_y
                        prev_was_long_or_g0 = True
                        outfile.write(line + "\n")
                        continue

                    # --- Вариант 2: Малое перемещение (< 10 мм) ---
                    step_size = 0.25
                    num_steps = max(1, math.ceil(segment_length / step_size))

                    sub_dx = dx / num_steps
                    sub_dy = dy / num_steps

                    # Проверяем, будет ли СЛЕДУЮЩАЯ линия длинной (смотрим наперед здесь нельзя,
                    # но мы можем плавно гасить шум к концу текущего отрезка, если бы знали.
                    # Для компенсации входа/выхода считаем расстояние до точек смены режима)

                    for step in range(1, num_steps + 1):
                        next_x = curr_x + sub_dx
                        next_y = curr_y + sub_dy

                        # 1. Генерируем чистый сдвиг из глобальной 4D карты
                        total_shift_x, total_shift_y = 0.0, 0.0
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
                        if prev_was_long_or_g0 and dist_from_start < blend_zone:
                            blend_factor = min(blend_factor, dist_from_start / blend_zone)

                        # Коэффициент не может быть меньше 0
                        blend_factor = max(0.0, blend_factor)

                        # Применяем сглаженный сдвиг
                        final_x = round(next_x + total_shift_x * blend_factor, 3)
                        final_y = round(next_y + total_shift_y * blend_factor, 3)

                        # Обновляем текущие идеальные координаты
                        curr_x, curr_y = next_x, next_y

                        # Собираем строку G-кода обратно
                        new_line = stripped
                        if x_match:
                            new_line = re.sub(r"X\s*[0-9.-]+", f"X{final_x}", new_line, flags=re.IGNORECASE)
                        if y_match:
                            new_line = re.sub(r"Y\s*[0-9.-]+", f"Y{final_y}", new_line, flags=re.IGNORECASE)

                        # Если в исходной строке был только один компонент, добавляем второй,
                        # так как шум смещает инструмент в обе стороны одновременно
                        if x_match and not y_match:
                            new_line += f" Y{final_y}"
                        elif y_match and not x_match:
                            new_line += f" X{final_x}"

                        outfile.write(new_line + "\n")

                    # После завершения цикла малых шагов фиксируем, что режим длинной линии отключен
                    prev_was_long_or_g0 = False
                    continue

            # Корректно отслеживаем координаты при холостом ходе G0
            if stripped.startswith("G0"):
                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)
                if x_match:
                    curr_x = float(x_match.group(1))
                if y_match:
                    curr_y = float(y_match.group(1))

                # Холостой ход сбрасывает накопление шума и фиксирует новую чистую границу
                last_boundary_x, last_boundary_y = curr_x, curr_y
                prev_was_long_or_g0 = True

            outfile.write(line + "\n")
