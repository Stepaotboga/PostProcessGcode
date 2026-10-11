import re
import os

def modify_z_properties(input_file, output_file, l=0.05, S=0.75, distance_to_pause=6000.0, z_limit=1.0):
    """Добавляет компенсацию z_offset и паузы для автоматического карандаша."""
    distance_to_zoffset = distance_to_pause * (l / S)
    distance_to_info = 200.0

    Z_OFFSET_GCODE = f'SET_GCODE_OFFSET Z_ADJUST=-0.05 ; Сдвиг Z каждые 1000 мм\nRESPOND TYPE=echo MSG="Z-offset auto-adjusted by -0.05mm ({round(distance_to_zoffset, 3)} mm path reached)"\n'
    PAUSE_GCODE = f'SET_GCODE_OFFSET Z=0.0\nRESPOND TYPE=echo MSG="PAUSE triggered: {round(distance_to_pause, 3)}mm path reached!"\nPAUSE\n'

    try:
        x_gcode_re = re.compile(r'X([-+]?[0-9]*\.?[0-9]+)')
        y_gcode_re = re.compile(r'Y([-+]?[0-9]*\.?[0-9]+)')
        z_gcode_re = re.compile(r'Z([-+]?[0-9]*\.?[0-9]+)')

        curr_x, curr_y, curr_z = None, None, None
        dist_1k = 0.0
        dist_10k = 0.0
        total_dist = 0.0
        dist_info = 0.0

        with open(input_file, 'r', encoding='utf-8') as f_in, \
                open(output_file, 'w', encoding='utf-8') as f_out:

            for line in f_in:
                cleaned_line = line.strip()

                if not cleaned_line or cleaned_line.startswith((';', '(')):
                    f_out.write(line)
                    continue

                comment_idx = cleaned_line.find(';')
                if comment_idx == -1: comment_idx = cleaned_line.find('(')
                gcode_part = cleaned_line if comment_idx == -1 else cleaned_line[:comment_idx]

                is_g1 = gcode_part.startswith('G1')

                match_x = x_gcode_re.search(gcode_part)
                match_y = y_gcode_re.search(gcode_part)
                match_z = z_gcode_re.search(gcode_part)

                new_x = float(match_x.group(1)) if match_x else curr_x
                new_y = float(match_y.group(1)) if match_y else curr_y
                if match_z:
                    curr_z = float(match_z.group(1))

                if is_g1 and curr_x is not None and curr_y is not None and curr_z is not None:
                    if curr_z < z_limit and (match_x or match_y):
                        dx = (new_x - curr_x) if match_x else 0.0
                        dy = (new_y - curr_y) if match_y else 0.0
                        dist = (dx ** 2 + dy ** 2) ** 0.5

                        dist_1k += dist
                        dist_10k += dist
                        total_dist += dist
                        dist_info += dist

                if match_x: curr_x = new_x
                if match_y: curr_y = new_y

                f_out.write(line)

                if dist_1k >= distance_to_zoffset:
                    f_out.write(Z_OFFSET_GCODE + "\n")
                    dist_1k -= distance_to_zoffset

                if dist_10k >= distance_to_pause:
                    f_out.write("G1 Z10\n" + PAUSE_GCODE + f"G1 Z{curr_z}" + "\n")
                    dist_10k -= distance_to_pause

                if dist_info >= distance_to_info:
                    f_out.write(f'\nRESPOND TYPE=echo MSG="пройдено: {round(total_dist, 3)}mm   до паузы: {round(distance_to_pause - dist_10k, 3)}mm    до оффсета:{round(distance_to_zoffset - dist_1k, 3)}mm"' + "\n")
                    dist_info = 0

            f_out.write(f"\n\n;Общая длина траектории: {total_dist} мм")
        return True, total_dist
    except Exception as e:
        return False, str(e)
