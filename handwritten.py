import math
import re

def get_smooth_noise(t):
    return (
        0.5 * math.sin(2 * t)
        + 0.3 * math.sin(5 * t + 1.2)
        + 0.2 * math.sin(11 * t + 0.7)
    )

def apply_smooth_jitter(dx, dy, time_step, config):
    if not config["use_smooth_noise"]:
        return 0.0, 0.0
    noise_x = get_smooth_noise(time_step)
    noise_y = get_smooth_noise(time_step + 123.45)
    return noise_x * config["max_jitter"], noise_y * config["max_jitter"]

def apply_directional_bias(dx, dy, config):
    if not config["use_directional_bias"]:
        return 0.0, 0.0
    if dx == 0 and dy == 0:
        return 0.0, 0.0
    angle = math.atan2(dy, dx)
    bias_factor = math.sin(angle) ** 2
    seed_noise = math.sin(angle * 10) * 0.5
    shift_x = seed_noise * config["directional_factor"] * bias_factor
    shift_y = seed_noise * config["directional_factor"] * bias_factor * 1.3
    return shift_x, shift_y

def process_noise(input_file, output_file, config):
    """Применяет искусственный шум  к файлу G-code."""
    x_re = re.compile(r"X\s*([0-9.-]+)", re.IGNORECASE)
    y_re = re.compile(r"Y\s*([0-9.-]+)", re.IGNORECASE)

    curr_x, curr_y = 0.0, 0.0
    time_step = 0.0

    with open(input_file, "r", encoding="utf-8") as infile, open(
        output_file, "w", encoding="utf-8"
    ) as outfile:

        for line in infile:
            stripped = line.strip()

            if stripped.startswith("G1"):
                x_match = x_re.search(stripped)
                y_re_match = y_re.search(stripped)

                if x_match or y_re_match:
                    next_x = float(x_match.group(1)) if x_match else curr_x
                    next_y = float(y_re_match.group(1)) if y_re_match else curr_y

                    dx = next_x - curr_x
                    dy = next_y - curr_y
                    time_step += config["noise_frequency"]

                    total_shift_x = 0.0
                    total_shift_y = 0.0

                    sx, sy = apply_smooth_jitter(dx, dy, time_step, config)
                    total_shift_x += sx
                    total_shift_y += sy

                    bx, by = apply_directional_bias(dx, dy, config)
                    total_shift_x += bx
                    total_shift_y += by

                    final_x = round(next_x + total_shift_x, 3)
                    final_y = round(next_y + total_shift_y, 3)
                    curr_x, curr_y = next_x, next_y

                    new_line = stripped
                    if x_match:
                        new_line = re.sub(r"X\s*[0-9.-]+", f"X{final_x}", new_line, flags=re.IGNORECASE)
                    if y_re_match:
                        new_line = re.sub(r"Y\s*[0-9.-]+", f"Y{final_y}", new_line, flags=re.IGNORECASE)

                    outfile.write(new_line + "\n")
                    continue

            if stripped.startswith("G0"):
                x_match = x_re.search(stripped)
                y_re_match = y_re.search(stripped)
                if x_match: curr_x = float(x_match.group(1))
                if y_re_match: curr_y = float(y_re_match.group(1))

            outfile.write(line + "\n")
