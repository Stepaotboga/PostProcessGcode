import sys
import os
import re
import webbrowser
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QLabel, QCheckBox, QGroupBox, QFormLayout,
    QDoubleSpinBox, QTextEdit, QTabWidget, QSlider
)
from PyQt5.QtCore import Qt
import pyqtgraph as pg


# Импортируем обновленные модули
from handwritten import process_noise
from v_offset import modify_z_properties

PEN_WIDTH_MM = 0.45            # толщина карандаша

BED_X, BED_Y = 400.0, 435.0   # рабочая область, мм
PEN_DOWN_Z = 1.0              # Z ниже этого значения = карандаш на бумаге

AXIS_RE = re.compile(r'([XYZ])\s*([-+]?\d*\.?\d+)', re.IGNORECASE)
CMD_RE = re.compile(r'^G(0|1|90|91)(?!\d)', re.IGNORECASE)

#default config
DEFAULT_CONST = {
    #МИКРО дрожания руки:
    "tremor_freq": 1.14, # Частота микро дрожи
    "tremor_amp": 0.18, # Амплитуда микродрожи  (мм)

    # Ступень 2: Уход высоты букв (Низкая частота, большая амплитуда)
    "height_freq": 0.09, # Частота Ступени 2: Уход высоты букв (Низкая частота, большая амплитуда)
    "height_amp": 0.41,  # Амплитуда (мм)

    # # Зоны плавного перехода fade (в миллиметрах)
    "fade_factor_1": 5.2,    # Расстояние полного нарастания для fade1  (мм)
    "fade_factor_2": 12.1,   # Расстояние полного нарастания для fade2  (мм)

    # Параметры для z_offset и паузы
    # Настройки при стирании карандаша
    "pause_dist": 5000.0,
    "defa_s": 0.75, # Выдвижение карандаша (S, мм):
    "defa_l": 0.05 # Стандартный z_offset (l, мм)
}


# Упрощение отрисовки предпросмотра gcode
def rdp_mask(pts, eps):
    n = len(pts)
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        seg = pts[i + 1:j]
        d = b - a
        L = np.hypot(d[0], d[1])
        if L == 0:
            dist = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1])
        else:
            dist = np.abs(d[0] * (seg[:, 1] - a[1]) - d[1] * (seg[:, 0] - a[0])) / L
        k = int(dist.argmax())
        if dist[k] > eps:
            k += i + 1
            keep[k] = True
            stack.append((i, k))
            stack.append((k, j))
    return keep


def simplify_nan_polyline(arr, eps=0.03):
    """Упрощает полилинии, разделённые NaN-строками."""
    if len(arr) == 0:
        return arr
    parts = np.split(arr, np.flatnonzero(np.isnan(arr[:, 0])))
    out = []
    for p in parts:
        if len(p) and np.isnan(p[0, 0]):
            p = p[1:]
        if len(p) == 0:
            continue
        if len(p) > 2:
            p = p[rdp_mask(p, eps)]
        out.append(p)
        out.append(np.array([[np.nan, np.nan]]))
    return np.vstack(out[:-1]) if out else arr


class GCodeConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_file = ""
        self.output_file = ""

        # Переменные для хранения данных 3D графики
        self.work_points = np.empty((0, 3), dtype=np.float32)
        self.retract_points = np.empty((0, 3), dtype=np.float32)
        self.work_plot = None
        self.retract_plot = None
        self.show_retracts = True

        pg.setConfigOptions(antialias=True) # сглаживание отображения

        self.initUI()

    def initUI(self):
        self.setWindowTitle('G-code Конвейер Модификаций с 3D Предпросмотром')
        # Увеличили размер окна под новые графические компоненты
        self.resize(1150, 850)

        main_layout = QHBoxLayout()
        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        # --- ЛЕВАЯ ПАНЕЛЬ: Управление и Настройки ---
        self.label = QLabel('<b>Файл не выбран</b>', self)
        self.btn_open = QPushButton('Выбрать G-code файл', self)
        self.btn_open.clicked.connect(self.open_file)

        self.group_modules = QGroupBox("Выбор обработок (выполняются сверху вниз):")
        mod_layout = QVBoxLayout()
        self.chk_noise = QCheckBox("1. Искусственный шум (Реалистичный почерк)")
        self.chk_noise.setChecked(True)
        self.chk_offset = QCheckBox("2. Вставка Z-Offset и пауз")
        self.chk_offset.setChecked(True)
        mod_layout.addWidget(self.chk_noise)
        mod_layout.addWidget(self.chk_offset)
        self.group_modules.setLayout(mod_layout)

        self.tabs = QTabWidget()

        # ВКЛАДКА НАСТРОЕК ДВУХУРОВНЕВОГО ШУМА
        tab_noise = QWidget()
        form_noise = QFormLayout()

        self.sp_tremor_freq = QDoubleSpinBox()
        self.sp_tremor_freq.setRange(0.1, 20.0)
        self.sp_tremor_freq.setValue(DEFAULT_CONST.get("tremor_freq", 5.0))
        self.sp_tremor_freq.setSingleStep(0.5)

        self.sp_tremor_amp = QDoubleSpinBox()
        self.sp_tremor_amp.setRange(0.0, 1.0)
        self.sp_tremor_amp.setValue(DEFAULT_CONST.get("tremor_amp", 0.03))
        self.sp_tremor_amp.setSingleStep(0.005)
        self.sp_tremor_amp.setDecimals(3)

        self.sp_height_freq = QDoubleSpinBox()
        self.sp_height_freq.setRange(0.01, 5.0)
        self.sp_height_freq.setValue(DEFAULT_CONST.get("height_freq", 0.12))
        self.sp_height_freq.setSingleStep(0.02)

        self.sp_height_amp = QDoubleSpinBox()
        self.sp_height_amp.setRange(0.0, 2.0)
        self.sp_height_amp.setValue(DEFAULT_CONST.get("height_amp", 0.28))
        self.sp_height_amp.setSingleStep(0.02)

        self.sp_fade_factor_1 = QDoubleSpinBox()
        self.sp_fade_factor_1.setRange(0.1, 50.0)
        self.sp_fade_factor_1.setValue(DEFAULT_CONST.get("fade_factor_1", 1.5))
        self.sp_fade_factor_1.setSingleStep(0.5)

        self.sp_fade_factor_2 = QDoubleSpinBox()
        self.sp_fade_factor_2.setRange(0.1, 50.0)
        self.sp_fade_factor_2.setValue(DEFAULT_CONST.get("fade_factor_2", 4.0))
        self.sp_fade_factor_2.setSingleStep(0.5)

        form_noise.addRow(QLabel("<b>Шаг 1: Микро-дрожание руки</b>"))
        form_noise.addRow("Частота дрожания (Tremor Freq):", self.sp_tremor_freq)
        form_noise.addRow("Амплитуда дрожания (Tremor Amp, мм):", self.sp_tremor_amp)
        form_noise.addRow(QLabel("<b>Шаг 2: Искажение высоты строк</b>"))
        form_noise.addRow("Частота волны букв (Height Freq):", self.sp_height_freq)
        form_noise.addRow("Амплитуда уплывания (Height Amp, мм):", self.sp_height_amp)
        form_noise.addRow(QLabel("<b>Параметры зон затухания (мм)</b>"))
        form_noise.addRow("Разгон/затухание дрожания (Fade 1):", self.sp_fade_factor_1)
        form_noise.addRow("Разгон/затухание волны (Fade 2):", self.sp_fade_factor_2)

        tab_noise.setLayout(form_noise)

        # Вкладка настроек ПАУЗЫ И СМЕЩЕНИЯ
        tab_offset = QWidget()
        form_offset = QFormLayout()
        self.sp_l = QDoubleSpinBox()
        self.sp_l.setRange(0.0, 10.0)
        self.sp_l.setValue(DEFAULT_CONST.get("defa_l", 0.05))
        self.sp_l.setDecimals(3)

        self.sp_S = QDoubleSpinBox()
        self.sp_S.setRange(0.0, 10.0)
        self.sp_S.setValue(DEFAULT_CONST.get("defa_s", 0.75))

        self.sp_pause_dist = QDoubleSpinBox()
        self.sp_pause_dist.setRange(100.0, 100000.0)
        self.sp_pause_dist.setValue(DEFAULT_CONST.get("pause_dist", 6000.0))
        self.sp_pause_dist.setSingleStep(500.0)

        form_offset.addRow("Стандартный z_offset (l, мм):", self.sp_l)
        form_offset.addRow("Выдвижение карандаша (S, мм):", self.sp_S)
        form_offset.addRow("Дистанция до паузы (мм):", self.sp_pause_dist)
        tab_offset.setLayout(form_offset)

        self.tabs.addTab(tab_noise, "Параметры шума")
        self.tabs.addTab(tab_offset, "Параметры смещения")

        self.btn_start = QPushButton('Запустить конвейер преобразования', self)
        self.btn_start.setStyleSheet("background-color: #2baf2b; color: white; font-weight: bold; height: 35px;")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.process_file)

        left_panel.addWidget(self.label)
        left_panel.addWidget(self.btn_open)
        left_panel.addWidget(self.group_modules)
        left_panel.addWidget(self.tabs)
        left_panel.addWidget(self.btn_start)

        # --- ПРАВАЯ ПАНЕЛЬ: Текст + 3D Визуализатор ---
        right_panel.addWidget(QLabel('<b>Предпросмотр итогового G-кода:</b>'))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(180)  # Ограничим по высоте, чтобы осталось место под 3D
        self.preview_text.setPlaceholderText("Здесь отобразится готовый код после обработки...")
        right_panel.addWidget(self.preview_text)

        # Интерфейс управления 3D интерактивным просмотром
        right_panel.addWidget(QLabel('<b>Интерактивный 3D Предпросмотр траектории плоттера:</b>'))

        # Виджет 3D графики OpenGL
        self.plot = pg.PlotWidget()
        self.plot.setAspectLocked(True)  # 1 мм по X = 1 мм по Y
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.getAxis('bottom').setTickSpacing(50, 10)  # крупная сетка 50 мм, мелкая 10 мм
        self.plot.getAxis('left').setTickSpacing(50, 10)
        self.plot.setLimits(xMin=-50, xMax=BED_X + 50, yMin=-50, yMax=BED_Y + 50)
        self.plot.setRange(xRange=(0, BED_X), yRange=(0, BED_Y), padding=0.03)

        # контур стола 400x435
        self.plot.addItem(pg.PlotCurveItem(
            [0, BED_X, BED_X, 0, 0], [0, 0, BED_Y, BED_Y, 0],
            pen=pg.mkPen((255, 200, 0), width=2)))

        work_pen = pg.mkPen(color=(0, 200, 255), width=PEN_WIDTH_MM, cosmetic=False)
        #work_pen.setCapStyle(Qt.RoundCap)  # скруглённые концы и стыки, как у грифеля
        #work_pen.setJoinStyle(Qt.RoundJoin)
        work_pen.setJoinStyle(Qt.BevelJoin)
        work_pen.setCapStyle(Qt.RoundCap)  # концы штрихов оставьте круглыми, их мало

        # две кривые: рабочая и холостая; 'finite' разрывает линию на NaN
        self.travel_curve = pg.PlotCurveItem(pen=pg.mkPen((255, 60, 60, 110), width=1), connect='finite')
        self.work_curve = pg.PlotCurveItem(pen=work_pen, connect='finite')
        self.plot.addItem(self.travel_curve)
        self.plot.addItem(self.work_curve)

        right_panel.addWidget(self.plot, stretch=1)

        # Панель управления 3D слоями и холостыми ходами
        view_ctrl_layout = QHBoxLayout()

        self.btn_toggle_retracts = QPushButton("Скрыть холостые ходы")
        self.btn_toggle_retracts.setCheckable(True)
        self.btn_toggle_retracts.clicked.connect(self.toggle_retracts_visibility)
        view_ctrl_layout.addWidget(self.btn_toggle_retracts)

        view_ctrl_layout.addWidget(QLabel("Послойная анимация:"))
        self.slider_layers = QSlider(Qt.Horizontal)
        self.slider_layers.setRange(0, 100)
        self.slider_layers.setValue(100)
        self.slider_layers.setEnabled(False)
        self.slider_layers.valueChanged.connect(self.update_layer_animation)
        view_ctrl_layout.addWidget(self.slider_layers)

        right_panel.addLayout(view_ctrl_layout)

        self.btn_nc_viewer = QPushButton('Визуализировать через движок NC Viewer')
        self.btn_nc_viewer.setStyleSheet("background-color: #0078d7; color: white;")
        self.btn_nc_viewer.setEnabled(False)
        self.btn_nc_viewer.clicked.connect(self.open_in_nc_viewer)
        right_panel.addWidget(self.btn_nc_viewer)

        main_layout.addLayout(left_panel, stretch=2)
        main_layout.addLayout(right_panel, stretch=3)
        self.setLayout(main_layout)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Открыть файл G-code', '', 'G-code файлы (*.gcode *.nc *.tap *.txt);;Все файлы (*)'
        )
        if file_path:
            self.selected_file = file_path
            self.label.setText(f"Выбран: <b>{os.path.basename(file_path)}</b>")
            self.btn_start.setEnabled(True)

    def process_file(self):
        if not self.selected_file:
            return

        # Задаем имя выходного файла
        dir_name, file_name = os.path.split(self.selected_file)
        name_part, ext_part = os.path.splitext(file_name)
        self.output_file = os.path.join(dir_name, f"{name_part}_modified{ext_part}")

        # Создаем цепочку временных файлов
        current_input = self.selected_file
        temp_noise_file = os.path.join(dir_name, "~temp_noise.gcode")

        try:
            # Шаг 1. Обработка ИСКУССТВЕННОГО ДВУХУРОВНЕВОГО ШУМА
            if self.chk_noise.isChecked():
                # Передаем конфигурацию, считанную напрямую из элементов графического окна интерфейса
                noise_config = {
                    "tremor_frequency": self.sp_tremor_freq.value(),
                    "tremor_amplitude": self.sp_tremor_amp.value(),
                    "height_frequency": self.sp_height_freq.value(),
                    "height_amplitude": self.sp_height_amp.value(),
                    "fade_factor_1": self.sp_fade_factor_1.value(),
                    "fade_factor_2": self.sp_fade_factor_2.value()
                }
                process_noise(current_input, temp_noise_file, noise_config)
                current_input = temp_noise_file

            # Шаг 2. Обработка СМЕЩЕНИЙ И ПАУЗ
            if self.chk_offset.isChecked():
                success, res_val = modify_z_properties(
                    input_file=current_input,
                    output_file=self.output_file,
                    l=self.sp_l.value(),
                    S=self.sp_S.value(),
                    distance_to_pause=self.sp_pause_dist.value()
                )
                if not success:
                    raise Exception(f"Ошибка в блоке z_offset: {res_val}")
                msg_text = f"Успешно обработано!\nОбщая длина траектории: {res_val:.2f} мм\nСохранено в: {os.path.basename(self.output_file)}"
            else:
                if current_input != self.selected_file:
                    os.replace(current_input, self.output_file)
                else:
                    QMessageBox.warning(self, "Предупреждение", "Ни одна обработка не выбрана!")
                    return
                msg_text = f"Обработка завершена (без Z-offset).\nСохранено в: {os.path.basename(self.output_file)}"

            # Удаляем временный файл шума, если он создавался
            if os.path.exists(temp_noise_file):
                os.remove(temp_noise_file)

            # Выводим сообщение об успехе
            #QMessageBox.information(self, 'Успех', msg_text)

            # Шаг 3. Загрузка в текстовое окно предпросмотра
            self.load_preview()
            self.parse_and_build_3d()  # Генерация 3D сцены
            self.btn_nc_viewer.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, 'Критическая ошибка', f"Произошел сбой при обработке:\n{str(e)}")
            if os.path.exists(temp_noise_file):
                os.remove(temp_noise_file)

    def load_preview(self):
        if not os.path.exists(self.output_file):
            return

        preview_lines = []
        with open(self.output_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i < 500:
                    preview_lines.append(line)
                else:
                    preview_lines.append("\n... [Код обрезан для экономии памяти предпросмотра] ...")
                    break
        self.preview_text.setPlainText("".join(preview_lines))

    def parse_and_build_3d(self):
        """Парсит итоговый G-code в две NaN-разделённые полилинии (XY)."""
        if not os.path.exists(self.output_file):
            return

        nan = (float('nan'), float('nan'))
        work, travel = [], []
        last = {'work': None, 'travel': None}

        def add(kind, buf, p0, p1):
            if last[kind] != p0:  # разрыв: начинаем новую линию
                if buf:
                    buf.append(nan)
                buf.append(p0)
            buf.append(p1)
            last[kind] = p1

        x, y, z = 0.0, 0.0, 20.0  # после G28 XY=0, Z заведомо поднят
        absolute = True

        with open(self.output_file, 'r', encoding='utf-8', errors='ignore') as f:
            for raw in f:
                line = raw.split(';', 1)[0]
                line = re.sub(r'\(.*?\)', '', line).strip()
                m = CMD_RE.match(line)
                if not m:
                    continue
                cmd = m.group(1)
                if cmd == '90':
                    absolute = True
                    continue
                if cmd == '91':
                    absolute = False
                    continue

                ax = {k.upper(): float(v) for k, v in AXIS_RE.findall(line)}
                nx, ny, nz = x, y, z
                if absolute:
                    nx, ny, nz = ax.get('X', x), ax.get('Y', y), ax.get('Z', z)
                else:
                    nx, ny, nz = x + ax.get('X', 0), y + ax.get('Y', 0), z + ax.get('Z', 0)

                if (nx, ny) != (x, y):
                    pen_down = (cmd == '1' and nz < PEN_DOWN_Z)
                    if pen_down:
                        add('work', work, (x, y), (nx, ny))
                    else:
                        add('travel', travel, (x, y), (nx, ny))
                x, y, z = nx, ny, nz

        #self.work_xy = np.array(work, dtype=np.float64).reshape(-1, 2)
        self.work_xy = simplify_nan_polyline(np.array(work, dtype=np.float64).reshape(-1, 2), eps=0.03)
        #self.travel_xy = np.array(travel, dtype=np.float64).reshape(-1, 2)
        self.travel_xy = simplify_nan_polyline(np.array(travel, dtype=np.float64).reshape(-1, 2), eps=0.03)

        self.travel_curve.setData(self.travel_xy[:, 0], self.travel_xy[:, 1])
        self.travel_curve.setVisible(self.show_retracts)
        self.update_layer_animation(100)

        self.slider_layers.setEnabled(len(self.work_xy) > 0)
        self.slider_layers.blockSignals(True)
        self.slider_layers.setValue(100)
        self.slider_layers.blockSignals(False)

    def toggle_retracts_visibility(self):
        self.show_retracts = not self.btn_toggle_retracts.isChecked()
        self.btn_toggle_retracts.setText(
            "Показать холостые ходы" if not self.show_retracts else "Скрыть холостые ходы")
        self.travel_curve.setVisible(self.show_retracts)

    def update_layer_animation(self, value):
        if not hasattr(self, 'work_xy'):
            return
        n = int(len(self.work_xy) * value / 100.0)
        self.work_curve.setData(self.work_xy[:n, 0], self.work_xy[:n, 1])

    def open_in_nc_viewer(self):
        if not self.output_file or not os.path.exists(self.output_file):
            QMessageBox.warning(self, "Ошибка", "Сначала сгенерируйте итоговый файл!")

            return
        url = "ncviewer.com"
        webbrowser.open(url)
        output_dir = os.path.dirname(os.path.abspath(self.output_file))
        os.startfile(output_dir)
        QMessageBox.information(
            self,
            "Просмотр в NC Viewer",
            f"1. В браузере открыт сайт NC Viewer.\n"
            f"2. Открыта папка с вашим файлом:\n{os.path.basename(self.output_file)}\n\n"
            f"Перетащите этот файл мышкой в окно браузера для 3D-визуализации."
        )

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = GCodeConverterApp()
    ex.show()
    sys.exit(app.exec_())