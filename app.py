import sys
import os
import webbrowser
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QLabel, QCheckBox, QGroupBox, QFormLayout,
    QDoubleSpinBox, QTextEdit, QTabWidget
)
from PyQt5.QtCore import Qt

# Импортируем обновленные модули
from handwritten import process_noise
from v_offset import modify_z_properties


class GCodeConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_file = ""
        self.output_file = ""
        self.initUI()

    def initUI(self):
        self.setWindowTitle('G-code Конвейер Модификаций')
        self.resize(750, 600)

        # Главный Layout разделен на Левую панель настроек и Правую панель предпросмотра
        main_layout = QHBoxLayout()
        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        # --- ЛЕВАЯ ПАНЕЛЬ: Управление и Настройки ---
        self.label = QLabel('<b>Файл не выбран</b>', self)
        self.btn_open = QPushButton('Выбрать G-code файл', self)
        self.btn_open.clicked.connect(self.open_file)

        # Чекбоксы модулей обработки
        self.group_modules = QGroupBox("Выбор обработок (выполняются сверху вниз):")
        mod_layout = QVBoxLayout()
        self.chk_noise = QCheckBox("1. Искусственный шум (Реалистичный почерк)")
        self.chk_noise.setChecked(True)
        self.chk_offset = QCheckBox("2. Вставка Z-Offset и пауз")
        self.chk_offset.setChecked(True)
        mod_layout.addWidget(self.chk_noise)
        mod_layout.addWidget(self.chk_offset)
        self.group_modules.setLayout(mod_layout)

        # Конфигурация параметров (Вкладки)
        self.tabs = QTabWidget()

        # Вкладка настроек ШУМА
        tab_noise = QWidget()
        form_noise = QFormLayout()
        self.sp_max_jitter = QDoubleSpinBox()
        self.sp_max_jitter.setRange(0.0, 5.0)
        self.sp_max_jitter.setValue(0.09)
        self.sp_max_jitter.setSingleStep(0.01)

        self.sp_noise_freq = QDoubleSpinBox()
        self.sp_noise_freq.setRange(0.0, 10.0)
        self.sp_noise_freq.setValue(0.3)
        self.sp_noise_freq.setSingleStep(0.05)

        self.chk_smooth_noise = QCheckBox()
        self.chk_smooth_noise.setChecked(True)
        self.chk_dir_bias = QCheckBox()
        self.chk_dir_bias.setChecked(True)
        self.sp_dir_factor = QDoubleSpinBox()
        self.sp_dir_factor.setRange(0.0, 5.0)
        self.sp_dir_factor.setValue(0.06)
        self.sp_dir_factor.setSingleStep(0.01)

        form_noise.addRow("Использовать плавное дрожание:", self.chk_smooth_noise)
        form_noise.addRow("Макс. отклонение Jitter (мм):", self.sp_max_jitter)
        form_noise.addRow("Частота шума (Frequency):", self.sp_noise_freq)
        form_noise.addRow("Зависимость от направления линии:", self.chk_dir_bias)
        form_noise.addRow("Сила искажения направления (Factor):", self.sp_dir_factor)
        tab_noise.setLayout(form_noise)

        # Вкладка настроек ПАУЗЫ И СМЕЩЕНИЯ
        tab_offset = QWidget()
        form_offset = QFormLayout()
        self.sp_l = QDoubleSpinBox()
        self.sp_l.setRange(0.0, 10.0)
        self.sp_l.setValue(0.05)
        self.sp_l.setDecimals(3)

        self.sp_S = QDoubleSpinBox()
        self.sp_S.setRange(0.0, 10.0)
        self.sp_S.setValue(0.75)

        self.sp_pause_dist = QDoubleSpinBox()
        self.sp_pause_dist.setRange(100.0, 100000.0)
        self.sp_pause_dist.setValue(6000.0)
        self.sp_pause_dist.setSingleStep(500.0)

        form_offset.addRow("Стандартный z_offset (l, мм):", self.sp_l)
        form_offset.addRow("Выдвижение карандаша (S, мм):", self.sp_S)
        form_offset.addRow("Дистанция до паузы (мм):", self.sp_pause_dist)
        tab_offset.setLayout(form_offset)

        self.tabs.addTab(tab_noise, "Параметры шума")
        self.tabs.addTab(tab_offset, "Параметры смещения")

        # Кнопка запуска
        self.btn_start = QPushButton('Запустить конвейер преобразования', self)
        self.btn_start.setStyleSheet("background-color: #2baf2b; color: white; font-weight: bold; height: 35px;")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.process_file)

        left_panel.addWidget(self.label)
        left_panel.addWidget(self.btn_open)
        left_panel.addWidget(self.group_modules)
        left_panel.addWidget(self.tabs)
        left_panel.addWidget(self.btn_start)

        # --- ПРАВАЯ ПАНЕЛЬ: Предпросмотр G-Code ---
        right_panel.addWidget(QLabel('<b>Предпросмотр итогового G-кода:</b>'))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Здесь отобразится готовый код после обработки...")
        right_panel.addWidget(self.preview_text)

        # Кнопка отправки в NC Viewer
        self.btn_nc_viewer = QPushButton('Визуализировать через движок NC Viewer')
        self.btn_nc_viewer.setStyleSheet("background-color: #0078d7; color: white;")
        self.btn_nc_viewer.setEnabled(False)
        self.btn_nc_viewer.clicked.connect(self.open_in_nc_viewer)
        right_panel.addWidget(self.btn_nc_viewer)

        # Сборка интерфейса
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

        # Шаг 0. Создаем цепочку временных файлов
        current_input = self.selected_file
        temp_noise_file = os.path.join(dir_name, "~temp_noise.gcode")

        try:
            # Шаг 1. Обработка ИСКУССТВЕННОГО ШУМА
            if self.chk_noise.isChecked():
                noise_config = {
                    "use_smooth_noise": self.chk_smooth_noise.isChecked(),
                    "max_jitter": self.sp_max_jitter.value(),
                    "noise_frequency": self.sp_noise_freq.value(),
                    "use_directional_bias": self.chk_dir_bias.isChecked(),
                    "directional_factor": self.sp_dir_factor.value()
                }
                process_noise(current_input, temp_noise_file, noise_config)
                current_input = temp_noise_file  # передаем измененный файл следующему скрипту

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
                # Если z_offset отключен, просто переносим результат работы шума (или исходника) в финальный файл
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
            self.btn_nc_viewer.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, 'Критическая ошибка', f"Произошел сбой при обработке:\n{str(e)}")
            if os.path.exists(temp_noise_file):
                os.remove(temp_noise_file)

    def load_preview(self):
        """Загружает первые 500 строк сгенерированного файла, чтобы интерфейс не зависал на больших файлах."""
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

    def open_in_nc_viewer(self):
        """Открывает браузер со ссылкой на онлайн-визуализатор NC Viewer."""
        if not self.output_file or not os.path.exists(self.output_file):
            QMessageBox.warning(self, "Ошибка", "Сначала сгенерируйте итоговый файл!")
            return

        # Так как ncviewer.com работает с локальными файлами через ручной Drag-and-Drop пользователя,
        # мы открываем сам сайт и напоминаем пользователю перетащить созданный файл туда.
        # Дополнительно открываем папку с созданным файлом для удобства перетаскивания.
        url = "ncviewer.com"
        webbrowser.open(url)
        # Открываем проводник с выделенным файлом
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