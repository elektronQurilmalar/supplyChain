# gui.py

import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import webbrowser
import os

from config_manager import save_api_keys, load_api_keys, SUPPORTED_APIS
from analyze import BOMAnalyzer


class ApiManagerWindow(ctk.CTkToplevel):
    """Окно для управления API ключами."""

    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)  # Окно будет поверх родительского
        self.grab_set()  # Модальное поведение
        self.title("Менеджер API ключей")
        self.geometry("500x350")
        self.parent = parent

        self.api_keys = load_api_keys()

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)

        self.entries = {}
        for i, api_name in enumerate(SUPPORTED_APIS):
            # Создаем фрейм для каждой строки
            frame = ctk.CTkFrame(self.main_frame)
            frame.pack(fill=ctk.X, padx=10, pady=5)

            label = ctk.CTkLabel(frame, text=f"{api_name.title()}:", width=80, anchor="w")
            label.pack(side=ctk.LEFT, padx=10)

            key = self.api_keys.get(api_name, "")
            entry = ctk.CTkEntry(frame, placeholder_text="API ключ не задан", width=300)
            if key:
                entry.insert(0, key)
            entry.pack(side=ctk.LEFT, expand=True, padx=10)
            self.entries[api_name] = entry

        self.save_button = ctk.CTkButton(self.main_frame, text="Сохранить и закрыть", command=self.save_and_close)
        self.save_button.pack(pady=20)

    def save_and_close(self):
        updated_keys = {api_name: entry.get() for api_name, entry in self.entries.items()}
        save_api_keys(updated_keys)
        self.parent.reload_config()  # Вызываем метод родителя для обновления
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Анализатор рисков BOM")
        self.geometry("600x450")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.api_keys = {}
        self.analyzer = None

        # --- Виджеты ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.pack(fill=ctk.BOTH, expand=True, padx=20, pady=20)

        top_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        top_frame.pack(fill=ctk.X, pady=(0, 10))

        self.api_status_label = ctk.CTkLabel(top_frame, text="Загрузка конфигурации...", font=ctk.CTkFont(size=12),
                                             text_color="gray")
        self.api_status_label.pack(side=ctk.LEFT)

        self.settings_button = ctk.CTkButton(top_frame, text="Настроить API", command=self.open_api_manager, width=120)
        self.settings_button.pack(side=ctk.RIGHT)

        self.label = ctk.CTkLabel(self.main_frame, text="Загрузите ваш BOM-файл в формате .csv",
                                  font=ctk.CTkFont(size=16, weight="bold"))
        self.label.pack(pady=10)

        self.load_button = ctk.CTkButton(self.main_frame, text="Выбрать BOM-файл...", command=self.load_bom,
                                         font=ctk.CTkFont(size=14))
        self.load_button.pack(pady=20, ipady=10)

        self.status_label = ctk.CTkLabel(self.main_frame, text="Ожидание файла...", font=ctk.CTkFont(size=12),
                                         text_color="gray")
        self.status_label.pack(pady=10, fill=ctk.X)

        self.after(100, self.reload_config)

    def reload_config(self):
        """Загружает ключи и проверяет готовность к работе."""
        self.api_keys = load_api_keys()
        active_keys = [name for name, key in self.api_keys.items() if key]

        if not active_keys:
            self.api_status_label.configure(text="Нет активных API ключей!", text_color="#E53935")
            self.load_button.configure(state="disabled")
            self.analyzer = None
            if messagebox.askyesno("Требуется настройка", "Не найден ни один API ключ. Хотите настроить сейчас?"):
                self.open_api_manager()
        else:
            status_text = f"Активные API: {', '.join(k.title() for k in active_keys)}"
            self.api_status_label.configure(text=status_text, text_color="green")
            self.load_button.configure(state="normal")
            try:
                self.analyzer = BOMAnalyzer(self.api_keys)
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e))
                self.analyzer = None
                self.load_button.configure(state="disabled")

    def open_api_manager(self):
        """Открывает окно управления ключами."""
        if not (hasattr(self, 'api_manager_window') and self.api_manager_window.winfo_exists()):
            self.api_manager_window = ApiManagerWindow(self)
        self.api_manager_window.focus()

    def load_bom(self):
        if not self.analyzer:
            messagebox.showerror("Ошибка", "Анализатор не инициализирован. Проверьте API ключи.")
            return

        file_path = filedialog.askopenfilename(
            title="Выберите BOM-файл",
            filetypes=(("CSV файлы", "*.csv"), ("Все файлы", "*.*"))
        )
        if not file_path:
            return

        self.load_button.configure(state="disabled")
        thread = threading.Thread(target=self.run_analysis, args=(file_path,), daemon=True)
        thread.start()

    def run_analysis(self, file_path):
        if self.analyzer:
            self.analyzer.process_bom_file(file_path, self.update_status)

        self.load_button.configure(state="normal")

        if messagebox.askyesno("Анализ завершен", "Отчет успешно создан. Хотите открыть его сейчас?"):
            try:
                webbrowser.open('file://' + os.path.realpath('bom_risk_report.html'))
            except Exception as e:
                self.update_status(f"Не удалось открыть отчет: {e}", "red")

    def update_status(self, message, color):
        """Безопасно обновляет текст и цвет статус-лейбла."""

        def _update():
            if color == "red":
                text_color = "#E53935"
            elif color == "green":
                text_color = "#43A047"
            else:
                text_color = "gray"
            self.status_label.configure(text=message, text_color=text_color)

        self.after(0, _update)