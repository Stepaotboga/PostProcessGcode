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
from PyQt5.QtGui import QVector3D
import pyqtgraph.opengl as gl

# Импортируем обновленные модули
from handwritten import process_noise
from v_offset import modify_z_properties

#default config
DEFAULT_CONST = {
    #МИКРО дрожания руки:
    "tremor_freq": 5.0, # Частота микро дрожи
    "tremor_amp": 0.06, # Амплитуда микродрожи  (мм)

    # Ступень 2: Уход высоты букв (Низкая частота, большая амплитуда)
    "height_freq": 0.09, # Частота Ступени 2: Уход высоты букв (Низкая частота, большая амплитуда)
    "height_amp": 0.68,  # Амплитуда (мм)

    # # Зоны плавного перехода fade (в миллиметрах)
    "fade_factor_1": 5.2,    # Расстояние полного нарастания для fade1  (мм)
    "fade_factor_2": 12.1,   # Расстояние полного нарастания для fade2  (мм)

    # Параметры для z_offset и паузы
    # Настройки при стирании карандаша
    "pause_dist": 5000.0,
    "defa_s": 0.75, # Выдвижение карандаша (S, мм):
    "defa_l": 0.05 # Стандартный z_offset (l, мм)
}


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
        self.gl_view = gl.GLViewWidget()
        self.gl_view.opts['distance'] = 120
        grid = gl.GLGridItem()
        grid.setSize(x=300, y=300, z=0)
        grid.setSpacing(x=10, y=10, z=0)
        self.gl_view.addItem(grid)
        right_panel.addWidget(self.gl_view, stretch=1)

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
            QMessageBox.information(self, 'Успех', msg_text)

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
        """Парсинг результирующего g-кода, разделение G0/G1 и заполнение массивов графики."""
        if not os.path.exists(self.output_file):
            return

        work_lst = []
        retract_lst = []
        curr_x, curr_y, curr_z = 0.0, 0.0, 0.0

        x_re = re.compile(r'X([-+]?[0-9]*\.?[0-9]+)')
        y_re = re.compile(r'Y([-+]?[0-9]*\.?[0-9]+)')
        z_re = re.compile(r'Z([-+]?[0-9]*\.?[0-9]+)')

        with open(self.output_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(';'):
                    continue

                if line.startswith('G0') or line.startswith('G1'):
                    is_g0 = line.startswith('G0')

                    match_x = x_re.search(line)
                    match_y = y_re.search(line)
                    match_z = z_re.search(line)

                    if match_x: curr_x = float(match_x.group(1))
                    if match_y: curr_y = float(match_y.group(1))
                    if match_z: curr_z = float(match_z.group(1))

                    if is_g0 or curr_z > 1.0:
                        retract_lst.append([curr_x, curr_y, curr_z])
                        retract_lst.append([np.nan, np.nan, np.nan])
                    else:
                        work_lst.append([curr_x, curr_y, curr_z])

        # Очищаем старые объекты со сцены
        if self.work_plot:
            self.gl_view.removeItem(self.work_plot)
        if self.retract_plot:
            self.gl_view.removeItem(self.retract_plot)

        self.work_points = np.array(work_lst, dtype=np.float32)
        self.retract_points = np.array(retract_lst, dtype=np.float32)

        # Создание рабочей траектории (Бирюзовый цвет)
        if len(self.work_points) > 0:
            work_colors = np.array([0.0, 0.8, 1.0, 0.9], dtype=np.float32)
            self.work_plot = gl.GLLinePlotItem(pos=self.work_points, color=work_colors, width=1.5, mode='line_strip')
            self.gl_view.addItem(self.work_plot)

            # ИСПРАВЛЕНО: Центрирование камеры с использованием QVector3D
            center = self.work_points.mean(axis=0)
            self.gl_view.setCameraPosition(pos=QVector3D(float(center[0]), float(center[1]), float(center[2])))

        # Создание холостых ходов (Блекло-красный цвет)
        if len(self.retract_points) > 0:
            retract_colors = np.array([1.0, 0.2, 0.2, 0.3], dtype=np.float32)
            self.retract_plot = gl.GLLinePlotItem(pos=self.retract_points, color=retract_colors, width=1.0,
                                                  mode='lines')
            if self.show_retracts:
                self.gl_view.addItem(self.retract_plot)

        if len(self.work_points) > 0:
            self.slider_layers.setEnabled(True)
            self.slider_layers.setValue(100)

    def toggle_retracts_visibility(self):
        """Прячет или показывает холостые траектории по клику на кнопку."""
        if self.btn_toggle_retracts.isChecked():
            self.btn_toggle_retracts.setText("Показать холостые ходы")
            self.show_retracts = False
            if self.retract_plot in self.gl_view.items:
                self.gl_view.removeItem(self.retract_plot)
        else:
            self.btn_toggle_retracts.setText("Скрыть холостые ходы")
            self.show_retracts = True
            if self.retract_plot and self.retract_plot not in self.gl_view.items:
                self.gl_view.addItem(self.retract_plot)

    def update_layer_animation(self, value):
        """Отрезает отрисовку рабочей траектории в зависимости от положения ползунка слайдера."""
        if self.work_plot is None or len(self.work_points) == 0:
            return

        limit_idx = int((value / 100.0) * len(self.work_points))
        if limit_idx < 2:
            current_visible_points = np.empty((0, 3), dtype=np.float32)
        else:
            current_visible_points = self.work_points[:limit_idx]

        self.work_plot.setData(pos=current_visible_points)

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