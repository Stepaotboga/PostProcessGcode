import math
import re
import os


num_perlins_noises = 2 #количество ступеней шума перлина



# Быстрая и независимая реализация шума Перлина (без сторонних библиотек)
class PerlinNoise:
    def __init__(self):
        # Таблица перестановок для создания стабильного псевдослучайного поля
        self.p = [
            151, 160, 137, 91, 90, 15, 131, 13, 201, 95, 96, 53, 194, 233, 7, 225, 140, 36, 103, 30, 69, 142, 8, 99, 37,
            240, 21, 10, 23,
            190, 6, 148, 247, 120, 234, 75, 0, 26, 197, 62, 94, 252, 219, 203, 117, 35, 11, 32, 57, 177, 33, 88, 237,
            149, 56, 87, 174,
            20, 125, 136, 171, 168, 68, 175, 74, 165, 71, 134, 139, 48, 27, 166, 77, 146, 158, 231, 83, 111, 229, 122,
            60, 211, 133,
            230, 220, 105, 92, 41, 55, 46, 245, 40, 244, 102, 143, 54, 65, 25, 63, 161, 1, 216, 80, 73, 209, 76, 132,
            187, 208, 89,
            18, 169, 200, 196, 135, 130, 116, 188, 159, 86, 164, 100, 109, 198, 173, 186, 3, 64, 52, 217, 226, 250, 124,
            123, 5, 202,
            38, 147, 118, 126, 255, 82, 85, 212, 207, 206, 59, 227, 47, 16, 58, 17, 182, 189, 28, 42, 223, 183, 170,
            213, 119, 248, 152,
            2, 44, 154, 163, 70, 221, 153, 101, 155, 167, 43, 172, 9, 129, 22, 39, 253, 19, 98, 108, 110, 79, 113, 224,
            232, 178, 185,
            112, 104, 218, 246, 97, 228, 251, 34, 242, 193, 238, 210, 144, 12, 191, 179, 162, 241, 81, 51, 145, 235,
            249, 14, 239,
            107, 49, 192, 214, 31, 181, 199, 106, 157, 184, 84, 204, 176, 115, 121, 50, 45, 127, 4, 150, 254, 138, 236,
            205, 93, 222,
            114, 67, 29, 24, 72, 243, 141, 128, 195, 78, 66, 215, 61, 156, 180
        ]
        self.p += self.p  # Дублируем массив для защиты от выхода за границы индекса

    def fade(self, t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    def lerp(self, t, a, b):
        return a + t * (b - a)

    def grad(self, hash_val, x, y):
        h = hash_val & 7
        u = x if h < 4 else y
        v = y if h < 4 else x
        return ((u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v))

    def noise2d(self, x, y):
        X = int(math.floor(x)) & 255
        Y = int(math.floor(y)) & 255
        x -= math.floor(x)
        y -= math.floor(y)
        u = self.fade(x)
        v = self.fade(y)
        A = self.p[X] + Y
        B = self.p[X + 1] + Y
        return self.lerp(v, self.lerp(u, self.grad(self.p[A], x, y),
                                      self.grad(self.p[B], x - 1, y)),
                         self.lerp(u, self.grad(self.p[A + 1], x, y - 1),
                                   self.grad(self.p[B + 1], x - 1, y - 1)))


# Инициализируем глобальный объект генератора
perlin = PerlinNoise()


def calculate_perlin_shifts(x, y, config, f1_val, f2_val):
    """
    Вычисляет результирующий двухкомпонентный сдвиг по осям X и Y.
    """
    # Ступень 1: Мелкое дрожание руки (Высокая частота, малая амплитуда)
    freq_tremor = config.get("tremor_frequency", 4.5)
    amp_tremor = config.get("tremor_amplitude", 0.04)  # до 0.04 мм

    # Смещаем сетку для Y, чтобы координаты не двигались синхронно по диагонали
    tremor_x = perlin.noise2d(x * freq_tremor, y * freq_tremor)
    tremor_y = perlin.noise2d(x * freq_tremor + 50.0, y * freq_tremor + 50.0)

    # Ступень 2: Удержание высоты букв / базовой линии (Низкая частота, большая амплитуда)
    freq_height = config.get("height_frequency", 0.15)
    amp_height = config.get("height_amplitude", 0.30)  # до 0.30 мм

    height_x = perlin.noise2d(x * freq_height, y * freq_height)
    height_y = perlin.noise2d(x * freq_height + 120.0, y * freq_height + 120.0)

    # Итоговый сдвиг — сумма двух октав, умноженная на свои индивидуальные fade-коэффициенты
    total_shift_x = (tremor_x * amp_tremor * f1_val) + (height_x * amp_height * f2_val)
    total_shift_y = (tremor_y * amp_tremor * f1_val) + (height_y * amp_height * f2_val)

    return total_shift_x, total_shift_y


def apply_perlin_noise_to_segmented_gcode(input_file, output_file, config):
    """
    Считывает готовый файл (где траектории уже разбиты на отрезки по 0.25 мм),
    извлекает значения fade1/fade2 и накладывает двухуровневый шум Перлина на координаты.
    """
    x_re = re.compile(r"X\s*([0-9.-]+)", re.IGNORECASE)
    y_re = re.compile(r"Y\s*([0-9.-]+)", re.IGNORECASE)

    # Паттерны для поиска коэффициентов затухания, сформированных на прошлых шагах
    fade1_pattern = r'\bfade1=([0-9.]+)'
    fade2_pattern = r'\bfade2=([0-9.]+)'

    # Координаты отслеживания идеального положения (без шума)
    curr_x, curr_y = 0.0, 0.0

    with open(input_file, "r", encoding="utf-8") as infile, open(
            output_file, "w", encoding="utf-8"
    ) as outfile:

        for line in infile:
            stripped = line.strip()

            # Обрабатываем только рабочие перемещения плоттера. Холостой ход G0 не трогаем.
            if stripped.startswith("G1"):
                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)

                # Обновляем наши идеальные опорные координаты
                target_x = float(x_match.group(1)) if x_match else curr_x
                target_y = float(y_match.group(1)) if y_match else curr_y

                f1_match = re.search(fade1_pattern, stripped)
                f2_match = re.search(fade2_pattern, stripped)

                # Если коэффициенты затухания найдены — берем их, иначе считаем равными 0.0
                f1_val = float(f1_match.group(1)) if f1_match else 0.0
                f2_val = float(f2_match.group(1)) if f2_match else 0.0

                # Применяем шум, только если хотя бы один коэффициент больше нуля
                if f1_val > 0 or f2_val > 0:
                    shift_x, shift_y = calculate_perlin_shifts(target_x, target_y, config, f1_val, f2_val)

                    final_x = round(target_x + shift_x, 3)
                    final_y = round(target_y + shift_y, 3)

                    # Модифицируем строку G-кода новыми зашумленными координатами
                    if x_match:
                        stripped = re.sub(r"X\s*[0-9.-]+", f"X{final_x}", stripped, flags=re.IGNORECASE)
                    else:
                        # Если координаты Х не было в команде (изменился только Y), добавляем её принудительно
                        stripped = re.sub(r"G1", f"G1 X{final_x}", stripped, flags=re.IGNORECASE)

                    if y_match:
                        stripped = re.sub(r"Y\s*[0-9.-]+", f"Y{final_y}", stripped, flags=re.IGNORECASE)
                    else:
                        # Если координаты Y не было в команде, добавляем её принудительно после X
                        stripped = re.sub(r"(X\s*[0-9.-]+)", r"\1" + f" Y{final_y}", stripped, flags=re.IGNORECASE)

                curr_x, curr_y = target_x, target_y

            # Обновляем координаты на холостых перемещениях G0, чтобы не накапливать ошибку
            elif stripped.startswith("G0"):
                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)
                if x_match: curr_x = float(x_match.group(1))
                if y_match: curr_y = float(y_match.group(1))

            outfile.write(stripped + "\n")


def process_noise(input_file, output_file, config):
    # Временные файлы для промежуточных этапов
    # 1. Получаем имя файла без расширения (например, из "C:/gcode/part.gcode" сделает "C:/gcode/part")
    base_dir, _ = os.path.splitext(input_file)

    # 2. Создаем папку, если она еще не существует (exist_ok=True защитит от ошибок, если папка уже есть)
    os.makedirs(base_dir, exist_ok=True)

    # 3. Извлекаем чистое имя файла с расширением для генерации имен внутри папки
    pure_filename = os.path.basename(input_file)
    filename_no_ext, _ = os.path.splitext(pure_filename)

    # 4. Формируем пути к временным файлам внутри созданной папки
    segments_tmp = os.path.join(
        base_dir, f"{filename_no_ext}_segments.gcode"
    )
    normal_tmp = os.path.join(base_dir, f"{filename_no_ext}_normal.gcode")
    faded_tmp = os.path.join(base_dir, f"{filename_no_ext}_faded.gcode")
    noise_tmp = os.path.join(
        base_dir, f"{filename_no_ext}_noise_applied.gcode"
    )

    # 1. Дробим отрезки
    segment_splitting(input_file, segments_tmp, config)
    print("segment_splitting done")

    # 2. Считаем плавный разгон fade
    calculate_fade_normal(segments_tmp, normal_tmp, config)
    print("calculate_fade_normal done")

    # 3. Считаем плавное затухание fade с конца траекторий
    calculate_fade_reverse(normal_tmp, faded_tmp, config)
    print("calculate_fade_reverse done")

    # 4. Накладываем шум Перлина на базе полученных fade коэффициентов
    apply_perlin_noise_to_segmented_gcode(faded_tmp, noise_tmp, config)
    print("perlin_noise done")

    # 5. Очищаем траекторию от слишком малых перемещений (последний обработчик)
    remove_small_movements(noise_tmp, output_file, min_distance=0.2)
    print(
        f"Шум наложен! Промежуточные файлы сохранены в папку: {base_dir}"
    )


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
                    stripped += f" fade1={round(curr_f1, 3)} "

                if f2_match:
                    fade2_target_mode = float(f2_match.group(1))
                    if fade2_target_mode == 0:
                        curr_f2 = 0.0
                    else:
                        # Строго линейный шаг для второго коэффициента
                        linear_step_2 = segment_length / max(fade_factor_2, 0.01)
                        curr_f2 = min(curr_f2 + linear_step_2, 1.0)

                    stripped = re.subn(fade2_remove_pattern, ' ', stripped)[0]
                    stripped += f" fade2={round(curr_f2, 3)} "

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
                stripped += f" fade1={round(final_f1, 3)} "

            if f2_match:
                normal_f2 = float(f2_match.group(1))

                if normal_f2 == 0:
                    curr_rf2 = 0.0
                else:
                    coeff = min(1, segment_length / max(fade_factor_2, 0.01))
                    curr_rf2 = min(curr_rf2 + coeff, 1.0) if normal_f2 > 0 else 0.0

                final_f2 = min(normal_f2, curr_rf2)

                stripped = re.sub(fade2_remove_pattern, ' ', stripped)
                stripped += f" fade2={round(final_f2, 3)} "

        out_file_data.append(stripped)

    # Записываем обратно в правильном (прямом) порядке
    with open(output_file, "w", encoding="utf-8") as outfile:
        for i in range(len(out_file_data) - 1, -1, -1):
            outfile.write(out_file_data[i] + "\n")


def segment_splitting(input_file, output_file, config):
    """
    Разбивает малые участки на сегменты по 0.25мм и сглаживает диагональные
    3D-подъемы (дорезку углов Aspire) по всем осям XYZ одновременно.
    Анализирует траекторию скользящим окном в 3 строки.
    """
    max_segment_length = 4.6
    conf_step_size = 0.25

    x_re = re.compile(r"X\s*([0-9.-]+)", re.IGNORECASE)
    y_re = re.compile(r"Y\s*([0-9.-]+)", re.IGNORECASE)
    z_re = re.compile(r"Z\s*([0-9.-]+)", re.IGNORECASE)

    # 1. Считываем весь файл в буфер строк
    with open(input_file, "r", encoding="utf-8") as infile:
        lines = infile.readlines()

    # Собираем точную сквозную историю координат плоттера для каждой строки
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

    out_lines = []
    prev_was_long = True
    l_lines = len(lines)

    # 2. Итерируемся по строкам с анализом трехточечного окна
    for i in range(l_lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("G1") and i > 0 and i < l_lines - 1:
            x_match = x_re.search(stripped)
            y_match = y_re.search(stripped)
            z_match = z_re.search(stripped)

            if x_match or y_match:
                # Точки окна: Предыдущая (A), Текущая (B), Следующая (C)
                ax, ay, az = coords[i - 1]
                bx, by, bz = coords[i]
                cx, cy, cz = coords[i + 1]

                # Векторы: AB (текущее движение) и BC (следующее движение)
                v1 = (bx - ax, by - ay, bz - az)
                v2 = (cx - bx, cy - by, cz - bz)

                len_v1 = math.hypot(*v1)
                len_v2 = math.hypot(*v2)

                # --- Вариант 1: Большое перемещение (не вмешиваемся в геометрию) ---
                if len_v1 >= max_segment_length or len_v1 == 0:
                    prev_was_long = True
                    out_lines.append(stripped + "; fade1=0 fade2=0")
                    continue

                # --- Вариант 2: Малое перемещение (Проверяем угол сопряжения) ---
                smooth_modifier = 1.0

                if len_v1 > 0.001 and len_v2 > 0.001:
                    # Скалярное произведение 3D векторов
                    dot_product = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
                    cos_angle = max(-1.0, min(1.0, dot_product / (len_v1 * len_v2)))
                    angle_deg = math.degrees(math.acos(cos_angle))

                    # Если угол изменения направления > 45 градусов,
                    # гасим уход фрезы по диагонали (XYZ) пропорционально остроте угла.
                    if angle_deg > 45.0:
                        # Чем ближе угол к 180 (полный разворот назад), тем ближе множитель к 0.1
                        smooth_modifier = max(0.1, (180.0 - angle_deg) / 135.0)

                # Дробим текущую траекторию на шаги по 0.25 мм
                step_size = conf_step_size
                num_steps = max(1, math.ceil(len_v1 / step_size))

                # Рассчитываем базовое приращение на микро-шаг
                sub_dx = v1[0] / num_steps * smooth_modifier
                sub_dy = v1[1] / num_steps * smooth_modifier
                sub_dz = v1[2] / num_steps * smooth_modifier

                for step in range(1, num_steps + 1):
                    # Если мы дошли до конечной точки сегмента (вершины угла дорезки),
                    # применяем сглаживающий множитель ко ВСЕМ осям XYZ
                    if step == num_steps:
                        next_x = ax + (sub_dx * step) * smooth_modifier
                        next_y = ay + (sub_dy * step) * smooth_modifier
                        next_z = az + (sub_dz * step) * smooth_modifier

                        # Корректируем историю координат для следующей итерации окна,
                        # чтобы плоттер не прыгал из измененной точки обратно на старую траекторию
                        coords[i] = (next_x, next_y, next_z)
                    else:
                        next_x = ax + sub_dx * step
                        next_y = ay + sub_dy * step
                        next_z = az + sub_dz * step

                    final_x = round(next_x, 3)
                    final_y = round(next_y, 3)
                    final_z = round(next_z, 3)

                    # Формируем строку обратно
                    new_line = stripped
                    if x_match:
                        new_line = re.sub(r"X\s*[0-9.-]+", f"X{final_x}", new_line, flags=re.IGNORECASE)
                    if y_match:
                        new_line = re.sub(r"Y\s*[0-9.-]+", f"Y{final_y}", new_line, flags=re.IGNORECASE)
                    if z_match:
                        new_line = re.sub(r"Z\s*[0-9.-]+", f"Z{final_z}", new_line, flags=re.IGNORECASE)

                    # Защита от потери осей в кадрах инкрементальных изменений
                    if x_match and not y_match:
                        new_line += f" Y{final_y}"
                    elif y_match and not x_match:
                        new_line += f" X{final_x}"

                    out_lines.append(new_line + "; fade1=1 fade2=1")

                prev_was_long = False
                continue

        # Не забываем про отслеживание пустых команд холостого хода G0
        if stripped.startswith("G0"):
            if prev_was_long:
                stripped += "; fade1=0 fade2=0"
            else:
                stripped += "; fade1=1 fade2=1"

        out_lines.append(stripped)

    # 3. Перезаписываем выходной файл
    with open(output_file, "w", encoding="utf-8") as outfile:
        for out_line in out_lines:
            outfile.write(out_line + "\n")


def remove_small_movements(input_file, output_file, min_distance=0.2):
    """
    Удаляет слишком малые перемещения G1 (меньше min_distance мм).
    Интерполирует (накапливает) перемещения по трем осям XYZ.
    Команды G0 всегда сбрасывают накопление и записываются как есть.
    """
    x_re = re.compile(r"X\s*([0-9.-]+)", re.IGNORECASE)
    y_re = re.compile(r"Y\s*([0-9.-]+)", re.IGNORECASE)
    z_re = re.compile(r"Z\s*([0-9.-]+)", re.IGNORECASE)

    # Текущая физическая позиция инструмента (последняя записанная в файл)
    curr_x, curr_y, curr_z = 0.0, 0.0, 0.0

    # Целевая позиция (куда должен прийти инструмент с учетом пропущенных точек)
    target_x, target_y, target_z = 0.0, 0.0, 0.0

    # Флаг, определяющий, были ли вообще инициализированы координаты в коде
    has_coords = False

    with open(input_file, "r", encoding="utf-8") as infile, open(
            output_file, "w", encoding="utf-8"
    ) as outfile:

        for line in infile:
            stripped = line.strip()

            if stripped.startswith("G1"):
                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)
                z_match = z_re.search(stripped)

                # Если это первая команда или осей не было, инициализируем их текущими значениями
                if not has_coords:
                    curr_x = float(x_match.group(1)) if x_match else 0.0
                    curr_y = float(y_match.group(1)) if y_match else 0.0
                    curr_z = float(z_match.group(1)) if z_match else 0.0
                    target_x, target_y, target_z = curr_x, curr_y, curr_z
                    has_coords = True
                    outfile.write(stripped + "\n")
                    continue

                # Обновляем потенциальную целевую точку
                if x_match: target_x = float(x_match.group(1))
                if y_match: target_y = float(y_match.group(1))
                if z_match: target_z = float(z_match.group(1))

                # Вычисляем расстояние в 3D пространстве от ПОСЛЕДНЕЙ ЗАПИСАННОЙ точки
                dx = target_x - curr_x
                dy = target_y - curr_y
                dz = target_z - curr_z
                distance = math.hypot(dx, dy, dz)

                if distance >= min_distance:
                    # Формируем новую строку с актуальными интерполированными координатами
                    new_line = stripped

                    # Перезаписываем или добавляем координаты в G1 кадр
                    if x_match:
                        new_line = re.sub(r"X\s*[0-9.-]+", f"X{round(target_x, 3)}", new_line, flags=re.IGNORECASE)
                    else:
                        new_line = re.sub(r"G1", f"G1 X{round(target_x, 3)}", new_line, flags=re.IGNORECASE)

                    if y_match:
                        new_line = re.sub(r"Y\s*[0-9.-]+", f"Y{round(target_y, 3)}", new_line, flags=re.IGNORECASE)
                    else:
                        new_line = re.sub(r"(X\s*[0-9.-]+)", r"\1" + f" Y{round(target_y, 3)}", new_line,
                                          flags=re.IGNORECASE)

                    if z_match:
                        new_line = re.sub(r"Z\s*[0-9.-]+", f"Z{round(target_z, 3)}", new_line, flags=re.IGNORECASE)
                    elif 'Z' in stripped or dz != 0:
                        # Если Z была в исходной строке или изменилась, добавляем в конец перед комментариями
                        if ";" in new_line:
                            new_line = re.sub(r";", f"Z{round(target_z, 3)} ;", new_line, count=1)
                        else:
                            new_line += f" Z{round(target_z, 3)}"

                    outfile.write(new_line + "\n")

                    # Смещаем текущую записанную позицию
                    curr_x, curr_y, curr_z = target_x, target_y, target_z
                else:
                    # Пропускаем строку (дистанция слишком мала), координаты аккумулируются в target_*
                    continue

            elif stripped.startswith("G0"):
                # При холостом ходе G0 принудительно записываем накопленный шаг (если он был)
                if has_coords and (curr_x != target_x or curr_y != target_y or curr_z != target_z):
                    # Восстанавливаем последнюю отброшенную точку перед G0, чтобы не потерять геометрию
                    outfile.write(f"G1 X{round(target_x, 3)} Y{round(target_y, 3)} Z{round(target_z, 3)}\n")

                x_match = x_re.search(stripped)
                y_match = y_re.search(stripped)
                z_match = z_re.search(stripped)

                if x_match: curr_x = target_x = float(x_match.group(1))
                if y_match: curr_y = target_y = float(y_match.group(1))
                if z_match: curr_z = target_z = float(z_match.group(1))
                has_coords = True

                outfile.write(stripped + "\n")
            else:
                # Все остальные команды (M3, M5, комментарии и т.д.) пишем без изменений
                outfile.write(stripped + "\n")
