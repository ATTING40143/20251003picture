# -*- coding: utf-8 -*-
import os
import sys
import time
import threading
import math
import shutil
import json
import datetime # 新增：用於產生時間戳
from PIL import Image, ImageDraw, ImageFont
import win32clipboard
import win32con
from io import BytesIO
import winreg
import hashlib
import tkinter as tk
from tkinter import messagebox, simpledialog
import traceback
import logging # 新增
import ctypes # 新增 DPI

# --- PyQt6 Imports ---
from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QDialog, 
                             QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, 
                             QDialogButtonBox, QLabel, QWidget, QMessageBox, QCheckBox, QDoubleSpinBox,
                             QHBoxLayout, QGraphicsDropShadowEffect, QPushButton, QFileDialog, QInputDialog)
from PyQt6.QtGui import QIcon, QAction, QActionGroup, QPainter, QColor, QPen, QCursor, QPixmap, QImage, QPainterPath, QMouseEvent
from PyQt6.QtCore import (QObject, pyqtSignal, QThread, Qt, QRect, QTimer, QRectF, QPointF, QLocale,
                          QPropertyAnimation, QEasingCurve, QEvent)

try:
    import mss
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("缺少模組", "找不到 'mss' 模組，請執行 'pip install mss' 安裝。")
    sys.exit(1)

try:
    import keyboard
except ImportError:
    # Handle missing keyboard module (same as original)
    error_title = "缺少必要模組"
    error_message = "錯誤：找不到 'keyboard' 模組！\n\n此程式需要該模組來監聽截圖快捷鍵。\n請開啟「命令提示字元」並執行以下指令來安裝：\n\npip install keyboard"
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(error_title, error_message)
    sys.exit(1)

try:
    import win32gui
    import win32console
    import win32api # 新增
    import win32ui      # 新增 for PrintWindow
    from ctypes import windll # 新增 for PrintWindow
    import win32con     # 新增 for GetDeviceCaps
    import win32print   # 新增 for GetDeviceCaps
except ImportError:
    print("警告：缺少 pywin32 模組，某些功能可能受限。請執行 'pip install pywin32' 進行安裝。")
    win32gui = None
    win32console = None
    win32api = None # 新增
    win32ui = None      # 新增
    windll = None     # 新增
    win32con = None     # 新增
    win32print = None   # 新增

# =============================================================================
# --- PyQt6 Dialogs ---
# =============================================================================

class SettingsDialog(QDialog):
    """設定浮水印文字、大小、透明度的對話框"""
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("設定浮水印")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self.settings = current_settings or {}

        # --- Widgets ---
        self.text_input = QLineEdit(self.settings.get('watermark_text', ''))
        self.size_input = QSpinBox()
        self.size_input.setRange(10, 100)
        self.size_input.setValue(self.settings.get('font_size', 25))
        self.opacity_input = QSpinBox()
        self.opacity_input.setRange(10, 255)
        self.opacity_input.setValue(self.settings.get('opacity', 128))

        self.show_notification_checkbox = QCheckBox()
        self.show_notification_checkbox.setChecked(self.settings.get('show_notifications', True))

        self.duration_input = QDoubleSpinBox()
        self.duration_input.setLocale(QLocale(QLocale.Language.English)) # Use dot for decimals
        self.duration_input.setRange(0.5, 10.0)
        self.duration_input.setSingleStep(0.1)
        self.duration_input.setSuffix(" 秒")
        # Convert ms from config to seconds for the dialog
        self.duration_input.setValue(self.settings.get('notification_duration_ms', 2000) / 1000.0)

        # --- 新增：自動儲存相關控制項 ---
        self.auto_save_checkbox = QCheckBox()
        self.auto_save_checkbox.setChecked(self.settings.get('auto_save_enabled', False))
        self.auto_save_checkbox.toggled.connect(self.on_auto_save_toggled)

        # 儲存路徑輸入框和瀏覽按鈕
        save_path_layout = QHBoxLayout()
        self.save_path_input = QLineEdit()
        default_save_path = self.settings.get('save_folder_path', os.path.join(os.path.expanduser("~"), "Desktop"))
        self.save_path_input.setText(default_save_path)
        self.save_path_input.setEnabled(self.auto_save_checkbox.isChecked())
        
        self.browse_button = QPushButton("瀏覽...")
        self.browse_button.clicked.connect(self.browse_save_folder)
        self.browse_button.setEnabled(self.auto_save_checkbox.isChecked())
        
        # 除錯：確認按鈕狀態
        print(f"瀏覽按鈕初始狀態 - 啟用: {self.browse_button.isEnabled()}, 自動儲存勾選: {self.auto_save_checkbox.isChecked()}")
        
        save_path_layout.addWidget(self.save_path_input)
        save_path_layout.addWidget(self.browse_button)

        # --- Layout ---
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow("浮水印文字:", self.text_input)
        form_layout.addRow("字體大小 (10-100):", self.size_input)
        form_layout.addRow("透明度 (10-255):", self.opacity_input)
        form_layout.addRow("顯示成功/失敗通知:", self.show_notification_checkbox)
        form_layout.addRow("通知顯示時間:", self.duration_input)
        form_layout.addRow("自動儲存圖片:", self.auto_save_checkbox)
        form_layout.addRow("儲存資料夾:", save_path_layout)
        layout.addLayout(form_layout)

        # --- Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def browse_save_folder(self):
        """開啟資料夾選擇對話框"""
        print("🔍 瀏覽按鈕被點擊了！")  # 除錯用
        
        try:
            current_path = self.save_path_input.text().strip()
            print(f"目前路徑: '{current_path}'")
            
            if not current_path or not os.path.exists(current_path):
                # 預設為桌面
                current_path = os.path.join(os.path.expanduser("~"), "Desktop")
                print(f"使用預設路徑: '{current_path}'")
            
            print("正在開啟資料夾選擇對話框...")
            
            # 使用最簡單的方式呼叫對話框
            folder = QFileDialog.getExistingDirectory(
                self, 
                "選擇儲存資料夾", 
                current_path
            )
            
            print(f"對話框返回結果: '{folder}'")
            
            if folder:  # 使用者選擇了資料夾且沒有取消
                self.save_path_input.setText(folder)
                print(f"✓ 已設定新路徑: {folder}")
            else:
                print("使用者取消了對話框或沒有選擇資料夾")
                
        except Exception as e:
            print(f"❌ 瀏覽資料夾時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            
            # 備用方案：使用簡單的輸入對話框
            try:
                text, ok = QInputDialog.getText(
                    self, 
                    '選擇儲存資料夾', 
                    '請輸入資料夾路徑:',
                    text=self.save_path_input.text()
                )
                if ok and text:
                    self.save_path_input.setText(text)
                    print(f"✓ 透過輸入對話框設定路徑: {text}")
            except Exception as e2:
                print(f"❌ 備用輸入對話框也失敗了: {e2}")
    
    def on_auto_save_toggled(self, checked):
        """當自動儲存開關變化時，啟用/禁用相關控制項"""
        print(f"🔄 自動儲存開關變更: {checked}")
        
        self.save_path_input.setEnabled(checked)
        self.browse_button.setEnabled(checked)
        
        print(f"瀏覽按鈕現在{'啟用' if checked else '禁用'}")
        
        # 如果啟用自動儲存但沒有設定路徑，則設定預設路徑為桌面
        if checked and not self.save_path_input.text():
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            self.save_path_input.setText(desktop_path)
            print(f"設定預設路徑: {desktop_path}")

    def get_settings(self):
        """返回使用者輸入的新設定"""
        return {
            'watermark_text': self.text_input.text(),
            'font_size': self.size_input.value(),
            'opacity': self.opacity_input.value(),
            'show_notifications': self.show_notification_checkbox.isChecked(),
            'notification_duration_ms': int(self.duration_input.value() * 1000),
            'auto_save_enabled': self.auto_save_checkbox.isChecked(),
            'save_folder_path': self.save_path_input.text()
        }

class HotkeyDetector(QObject):
    """在背景執行緒中偵測鍵盤事件的 Worker"""
    update_display = pyqtSignal(str)
    hotkey_detected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        pressed_keys = set()
        final_hotkey_combo = ""
        
        name_mapping = {
            'left windows': 'win', 'right windows': 'win',
            'left control': 'ctrl', 'right control': 'ctrl',
            'left shift': 'shift', 'right shift': 'shift',
            'left alt': 'alt', 'right alt': 'alt',
        }
        modifier_order = ['win', 'ctrl', 'alt', 'shift']

        while self.running:
            try:
                event = keyboard.read_event(suppress=True)
            except (EOFError, KeyboardInterrupt):
                break

            if not self.running:
                break
            
            normalized_name = name_mapping.get(event.name, event.name)

            if event.event_type == keyboard.KEY_DOWN:
                pressed_keys.add(normalized_name)
                
                modifiers = sorted([k for k in pressed_keys if k in modifier_order], key=modifier_order.index)
                others = sorted([k for k in pressed_keys if k not in modifier_order])
                
                current_keys_list = modifiers + others
                display_str = " + ".join(current_keys_list)
                
                self.update_display.emit(f"偵測到: {display_str.upper()}")
                final_hotkey_combo = display_str

            elif event.event_type == keyboard.KEY_UP:
                if normalized_name in pressed_keys:
                    pressed_keys.remove(normalized_name)
                
                if not pressed_keys and final_hotkey_combo:
                    self.hotkey_detected.emit(final_hotkey_combo)
                    break 
        
        print("Hotkey detector thread finished.")

    def stop(self):
        self.running = False


class HotkeyDialog(QDialog):
    """設定快捷鍵的對話框，使用背景執行緒處理鍵盤監聽"""
    def __init__(self, parent=None, current_hotkey=""):
        super().__init__(parent)
        self.setWindowTitle("設定快捷鍵")
        self.setFixedSize(350, 150)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        self.new_hotkey = None

        # --- Widgets ---
        self.info_label = QLabel(f"目前的快捷鍵: {current_hotkey.upper()}\n\n請按下您想設定的新快捷鍵組合...")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setWordWrap(True)
        
        font = self.info_label.font()
        font.setPointSize(12)
        self.info_label.setFont(font)

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        
        # --- Threading Setup ---
        self.thread = QThread()
        self.detector = HotkeyDetector()
        self.detector.moveToThread(self.thread)
        
        self.thread.started.connect(self.detector.run)
        self.detector.update_display.connect(self.update_info_label)
        self.detector.hotkey_detected.connect(self.on_hotkey_finished)
        
        self.finished.connect(self.cleanup)
        
        self.thread.start()

    def update_info_label(self, text):
        self.info_label.setText(text)

    def on_hotkey_finished(self, hotkey):
        self.new_hotkey = hotkey
        self.accept()

    def cleanup(self):
        """確保執行緒安全退出"""
        if self.thread.isRunning():
            print("Cleaning up hotkey dialog resources...")
            self.detector.stop()
            self.thread.quit()
            self.thread.wait(500) # Wait up to 500ms

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class CustomNotification(QWidget):
    """一個自訂的、非原生的通知視窗 (Toast)"""
    def __init__(self, title, message, icon_type='info', duration_ms=2000, parent=None):
        super().__init__(parent)
        self.duration_ms = duration_ms

        # --- 視窗設定 ---
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) # 記憶體管理很重要
        self.setFixedSize(350, 100)

        # --- 背景與主要佈局 ---
        self.bg_widget = QWidget(self)
        self.bg_widget.setObjectName("backgroundWidget") # 給予一個唯一的物件名稱
        self.bg_widget.setGeometry(5, 5, self.width() - 10, self.height() - 10)
        # 使用 ID 選擇器 (#) 來確保樣式只應用於這個特定的 widget
        self.bg_widget.setStyleSheet("""
            QWidget#backgroundWidget {
                background-color: #2E2E2E;
                border-radius: 8px;
                border: 1px solid #555555;
            }
        """)

        # --- 陰影效果 ---
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)
        
        # --- 元件 ---
        self.icon_label = QLabel(self.bg_widget)
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 強制設定背景透明無邊框
        self.icon_label.setStyleSheet("background: transparent; border: none;")

        self.title_label = QLabel(title, self.bg_widget)
        self.title_label.setObjectName("title")
        self.title_label.setStyleSheet("QLabel#title { background: transparent; border: none; color: white; font-size: 16px; font-weight: bold; }")

        self.message_label = QLabel(message, self.bg_widget)
        self.message_label.setObjectName("message")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("QLabel#message { background: transparent; border: none; color: #CCCCCC; font-size: 14px; }")

        self.set_icon(icon_type)

        # --- 佈局 ---
        main_layout = QHBoxLayout(self.bg_widget)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)
        
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(10, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.message_label)
        main_layout.addLayout(text_layout)
        
        # 用於淡出的計時器
        QTimer.singleShot(self.duration_ms, self.start_fade_out)

    def set_icon(self, icon_type):
        pixmap = QPixmap(self.icon_label.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if icon_type == 'success':
            painter.setPen(QPen(QColor("#4CAF50"), 4)) # 綠色
            painter.drawLine(10, 20, 18, 28)
            painter.drawLine(18, 28, 30, 12)
        elif icon_type == 'warning':
            painter.setPen(QPen(QColor("#FFC107"), 3)) # 黃色
            path = QPainterPath()
            path.moveTo(20, 8)
            path.lineTo(35, 32)
            path.lineTo(5, 32)
            path.closeSubpath()
            painter.drawPath(path)
            painter.setBrush(QColor("#FFC107"))
            painter.drawEllipse(18, 24, 4, 4)
            painter.drawRect(18, 14, 4, 8)
        else: # info
            painter.setPen(QPen(QColor("#2196F3"), 3)) # 藍色
            painter.drawEllipse(5, 5, 30, 30)
            painter.setBrush(QColor("#2196F3"))
            painter.drawEllipse(18, 10, 4, 4)
            painter.drawRect(18, 18, 4, 12)
            
        painter.end()
        self.icon_label.setPixmap(pixmap)

    def show_notification(self):
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        pos_x = screen_geometry.right() - self.width() - 15
        pos_y = screen_geometry.bottom() - self.height() - 15
        self.move(pos_x, pos_y)
        self.show()

    def start_fade_out(self):
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(500) # 0.5 秒淡出
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.animation.finished.connect(self.close)
        self.animation.start()


# =============================================================================
# --- Screenshot Overlay ---
# =============================================================================

class ScreenshotOverlay(QWidget):
    """一個無邊框、半透明的視窗，用於選擇截圖區域"""
    screenshot_taken = pyqtSignal(Image.Image)

    def __init__(self):
        super().__init__()
        self.full_screenshot = None
        self.full_pixmap = None
        self.selection_rect = QRect()
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.mode_selection_active = True # 新增：初始為模式選擇階段
        self.is_clicking = False # 新增：防止重複觸發
        self.click_check_timer = None # 新增：點擊偵測計時器
        
        # --- 新增：視窗擷取模式相關屬性 ---
        self.capture_mode = None # 'region', 'fullscreen', 或 'window'
        self.highlighted_window_geom = None # 儲存高亮視窗的螢幕座標 (l, t, r, b)
        self.highlighted_window_hwnd = None # 新增：儲存高亮視窗的句柄
        self.highlighted_window_ratio = 1.0 # 新增：儲存高亮視窗所在螢幕的縮放比例
        self.last_hwnd = None
        self.own_hwnd = None # 覆蓋層自身的視窗句柄
        self.mouse_grabbed = False # 新增：追蹤滑鼠抓住狀態
        
        # --- 新增：ESC 鍵全域監聽器 ---
        self.esc_thread = None
        self.esc_listener = None

        # --- 獲取虛擬螢幕的實體像素資訊 ---
        if win32api:
            # --- 新增：記錄詳細的螢幕資訊 ---
            try:
                all_screens_info = ""
                monitors = win32api.EnumDisplayMonitors()
                for i, monitor_info in enumerate(monitors):
                    h_monitor = monitor_info[0]
                    info = win32api.GetMonitorInfo(h_monitor)
                    device_name = info['Device']
                    
                    hDC = win32gui.CreateDC(device_name, None, None)
                    # 獲取水平和垂直方向的邏輯像素密度
                    logical_pixels_x = win32print.GetDeviceCaps(hDC, win32con.LOGPIXELSX)
                    win32gui.DeleteDC(hDC)
                    scale = logical_pixels_x / 96.0 # 96 DPI is the default
                    
                    all_screens_info += (
                        f"\n  [螢幕 {i+1}] - 裝置: {info['Device']}"
                        f"\n    - 實體解析度: {info['Monitor'][2]}x{info['Monitor'][3]}"
                        f"\n    - 縮放比例: {scale*100:.0f}%"
                    )
                logging.info(f"偵測到以下螢幕組態:{all_screens_info}")
            except Exception as e:
                logging.error(f"偵測詳細螢幕資訊時出錯: {e}", exc_info=True)


            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            SM_CXVIRTUALSCREEN = 78
            SM_CYVIRTUALSCREEN = 79
            
            x = win32api.GetSystemMetrics(SM_XVIRTUALSCREEN)
            y = win32api.GetSystemMetrics(SM_YVIRTUALSCREEN)
            width = win32api.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            height = win32api.GetSystemMetrics(SM_CYVIRTUALSCREEN)
            self.virtual_screen_rect = QRect(x, y, width, height)
            logging.info(f"偵測到實體虛擬螢幕尺寸: {self.virtual_screen_rect.width()}x{self.virtual_screen_rect.height()} @ ({self.virtual_screen_rect.x()},{self.virtual_screen_rect.y()})")
        else:
            logging.warning("無法使用 win32api 獲取螢幕資訊，可能因縮放導致顯示錯誤。")
            # 備用方案：使用 PyQt 的方法，但在高 DPI 下可能不準確
            self.virtual_screen_rect = QApplication.primaryScreen().virtualGeometry()

        # --- 關鍵修正：手動計算符合 DPI 縮放的邏輯幾何尺寸 ---
        # 這樣 PyQt 在內部放大後，視窗的實體尺寸才會是我們想要的
        primary_screen = QApplication.primaryScreen()
        ratio = primary_screen.devicePixelRatio() if primary_screen else 1.0
        if not ratio or ratio == 0: ratio = 1.0

        logical_rect = QRect(
            int(self.virtual_screen_rect.x() / ratio),
            int(self.virtual_screen_rect.y() / ratio),
            int(self.virtual_screen_rect.width() / ratio),
            int(self.virtual_screen_rect.height() / ratio)
        )
        logging.info(f"實體像素: {self.virtual_screen_rect}, 縮放比例: {ratio}, 計算後的邏輯像素: {logical_rect}")
        self.setGeometry(logical_rect) 

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |       # 無邊框
            Qt.WindowType.WindowStaysOnTopHint |      # 總在最上
            Qt.WindowType.Tool                        # 不在任務欄顯示圖示
        )
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True) # 方案一：註解此行，改用不透明視窗
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # 方案一：允許視窗接收鍵盤焦點
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptDrops, False) # 不接受拖放
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True) # 啟用輸入法支援
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True) # 持續追蹤滑鼠

        # --- 設定工具列幾何資訊 ---
        toolbar_width = 680 # 增加寬度以容納圖示和 ESC 提示
        toolbar_height = 55
        
        # 獲取主螢幕的幾何資訊
        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            primary_geometry = primary_screen.geometry()
            # 計算主螢幕水平中央，垂直位置在上方
            toolbar_x = primary_geometry.x() + (primary_geometry.width() - toolbar_width) // 2
            toolbar_y = primary_geometry.y() + 80  # 距離主螢幕頂部80像素
        else:
            # 備用方案：如果無法獲取主螢幕資訊，使用原來的方法
            toolbar_x = (self.virtual_screen_rect.width() - toolbar_width) / 2
            toolbar_y = 30
        
        self.toolbar_rect = QRect(int(toolbar_x), int(toolbar_y), toolbar_width, toolbar_height)
        
        # 重新計算按鈕位置：移除圖示，讓按鈕填滿左側空間
        esc_text_width = 180 # 右邊 ESC 提示區域寬度
        total_padding = 40 # (左右各 10, 按鈕間距 10*2)
        available_width = toolbar_width - esc_text_width - total_padding
        button_width = available_width // 3
        button_height = toolbar_height - 16
        button_y = self.toolbar_rect.top() + 8
        
        # 按鈕從最左邊開始排列
        first_button_x = self.toolbar_rect.left() + 10
        self.region_button_rect = QRect(first_button_x, button_y, button_width, button_height)
        self.window_button_rect = QRect(self.region_button_rect.right() + 10, button_y, button_width, button_height)
        self.fullscreen_button_rect = QRect(self.window_button_rect.right() + 10, button_y, button_width, button_height)
        
        # 定義 ESC 提示的區域
        self.esc_text_rect = QRect(self.fullscreen_button_rect.right() + 10, button_y, esc_text_width, button_height)

        # --- 擷取螢幕 ---
        self.capture_screen()
    
    def showEvent(self, event):
        """當視窗顯示時，強制獲取焦點並設定 Pixmap"""
        super().showEvent(event)
        # --- 方案一：強制獲取鍵盤與滑鼠焦點 ---
        self.activateWindow()
        self.setFocus()
        
        # --- 新增：使用 QTimer 延遲確保焦點設定 ---
        QTimer.singleShot(50, self._ensure_focus)
        
        # --- 新增：啟動 ESC 鍵全域監聽器 ---
        self._setup_esc_listener()

        if self.own_hwnd is None and win32gui:
            self.own_hwnd = int(self.winId())
            logging.info(f"Overlay HWND: {self.own_hwnd}")
        
        if self.full_pixmap:
            # 告訴 QPixmap 它的解析度是基於實體像素，以確保在高 DPI 螢幕上正確繪製
            screen = self.screen()
            if screen:
                ratio = screen.devicePixelRatio()
                logging.info(f"設定 QPixmap 的 devicePixelRatio 為: {ratio}")
                self.full_pixmap.setDevicePixelRatio(ratio)
    
    def _ensure_focus(self):
        """延遲確保視窗獲得焦點，以便 ESC 鍵能正常工作"""
        self.raise_()  # 將視窗提升到最前面
        self.activateWindow()  # 啟動視窗
        self.setFocus(Qt.FocusReason.OtherFocusReason)  # 設定鍵盤焦點
        
        # 在模式選擇階段，使用更強制的方法確保焦點
        if self.mode_selection_active:
            # 使用 QTimer 再次延遲確保焦點，特別針對工具列階段
            QTimer.singleShot(100, self._force_focus_for_toolbar)
            
        logging.debug("視窗焦點已重新設定，ESC 鍵應可正常工作")
    
    def _force_focus_for_toolbar(self):
        """專門為工具列階段強制設定焦點"""
        if self.mode_selection_active:  # 確保仍在工具列階段
            self.raise_()
            self.activateWindow() 
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            # 嘗試使用 Windows API 強制設定焦點（如果可用）
            if win32gui and self.own_hwnd:
                try:
                    win32gui.SetForegroundWindow(self.own_hwnd)
                    win32gui.SetFocus(self.own_hwnd)
                except Exception as e:
                    logging.debug(f"Windows API 焦點設定失敗: {e}")
            logging.debug("工具列階段焦點已強制設定")

    def _setup_esc_listener(self):
        """設定 ESC 鍵全域監聽器"""
        if self.esc_thread and self.esc_thread.isRunning():
            return  # 已經在運行
            
        self.esc_thread = QThread()
        self.esc_listener = GlobalEscListener()
        self.esc_listener.moveToThread(self.esc_thread)
        
        # 連接信號
        self.esc_thread.started.connect(self.esc_listener.run)
        self.esc_listener.esc_pressed.connect(self._on_global_esc)
        
        # 啟動執行緒
        self.esc_thread.start()
        logging.info("✓ ESC 鍵全域監聽器已啟動")
    
    def _on_global_esc(self):
        """處理全域 ESC 鍵事件"""
        logging.info("🔥 全域 ESC 鍵被偵測到！取消截圖。")
        self.close()
    
    def _cleanup_esc_listener(self):
        """清理 ESC 鍵監聽器"""
        if self.esc_listener and self.esc_thread:
            logging.info("正在停止 ESC 鍵監聽器...")
            self.esc_listener.stop()
            self.esc_thread.quit()
            self.esc_thread.wait(1000)
            logging.info("✓ ESC 鍵監聽器已停止")

    def capture_screen(self):
        """使用 mss 擷取整個虛擬螢幕"""
        try:
            with mss.mss() as sct:
                monitor = {
                    "top": self.virtual_screen_rect.top(), 
                    "left": self.virtual_screen_rect.left(), 
                    "width": self.virtual_screen_rect.width(), 
                    "height": self.virtual_screen_rect.height()
                }
                sct_img = sct.grab(monitor)
                # 將 BGRA 轉換為 RGBA for PIL
                self.full_screenshot = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                # 將 PIL Image 轉換為 QPixmap 以便繪製
                q_image = QImage(self.full_screenshot.tobytes(), self.full_screenshot.width, self.full_screenshot.height, QImage.Format.Format_RGB888)
                self.full_pixmap = QPixmap.fromImage(q_image)

        except Exception as e:
            logging.error(f"✗ 螢幕擷取失敗: {e}", exc_info=True)
            self.close()

    def paintEvent(self, event):
        """繪製背景、遮罩和選取框 (針對不透明視窗優化)"""
        if not self.full_pixmap:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. 繪製完整的螢幕截圖作為背景
        painter.drawPixmap(self.rect(), self.full_pixmap)
        
        # 2. 確定需要高亮的區域和邊框樣式
        highlight_rect = QRectF()
        highlight_pen = QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.SolidLine)
        
        if self.capture_mode == 'window' and self.highlighted_window_geom:
            # 視窗模式：高亮偵測到的視窗
            left, top, right, bottom = self.highlighted_window_geom # 這是實體像素座標
            
            ratio = self.highlighted_window_ratio
            if not ratio or ratio == 0: ratio = 1.0

            # 計算相對於覆蓋層的本地邏輯座標
            overlay_physical_x = self.virtual_screen_rect.x()
            overlay_physical_y = self.virtual_screen_rect.y()
            relative_physical_x = left - overlay_physical_x
            relative_physical_y = top - overlay_physical_y
            local_logical_x = relative_physical_x / ratio
            local_logical_y = relative_physical_y / ratio
            logical_width = (right - left) / ratio
            logical_height = (bottom - top) / ratio

            highlight_rect = QRectF(local_logical_x, local_logical_y, logical_width, logical_height)
            highlight_pen = QPen(QColor("#3399FF"), 3, Qt.PenStyle.SolidLine)

        elif self.capture_mode == 'region' and not self.selection_rect.isNull():
            # 區域模式：高亮使用者拖曳的矩形
            highlight_rect = QRectF(self.selection_rect)

        # 3. 建立一個遮罩路徑：從整個視窗區域中「減去」高亮區域
        mask_path = QPainterPath()
        mask_path.setFillRule(Qt.FillRule.OddEvenFill)
        mask_path.addRect(QRectF(self.rect())) # 整個視窗
        if not highlight_rect.isNull():
            mask_path.addRect(highlight_rect) # 「減去」高亮區域

        # 4. 在遮罩路徑上繪製半透明黑色
        mask_color = QColor(0, 0, 0, 120)
        painter.fillPath(mask_path, mask_color)
        
        # 5. 如果有高亮區域，繪製其邊框
        if not highlight_rect.isNull():
            painter.setPen(highlight_pen)
            painter.drawRect(highlight_rect)

        # 6. 如果是模式選擇階段，繪製工具列
        if self.mode_selection_active:
            self.draw_toolbar(painter)

    def draw_toolbar(self, painter):
        """繪製模式選擇工具列"""
        # 設定顏色和字體
        toolbar_bg_color = QColor("#2E2E2E")
        toolbar_border_color = QColor(Qt.GlobalColor.white)
        button_bg_color = QColor("#4A4A4A")
        text_color = QColor(Qt.GlobalColor.white)
        
        font = self.font()
        font.setFamily("Microsoft JhengHei UI")
        font.setPointSize(16)
        painter.setFont(font)
        
        # 繪製工具列背景
        painter.setBrush(toolbar_bg_color)
        painter.setPen(toolbar_border_color)
        painter.drawRect(self.toolbar_rect)
        
        # --- 通用按鈕繪製邏輯 ---
        def draw_button_with_icon(button_rect, icon_func, text):
            painter.setBrush(button_bg_color)
            painter.setPen(toolbar_border_color) # 確保每個按鈕都有邊框
            painter.drawRect(button_rect)

            # 將按鈕區域分割為圖示區和文字區
            icon_size = button_rect.height() - 10 # 圖示大小比按鈕高度小一點
            icon_rect = QRect(
                button_rect.left() + 10,
                button_rect.top() + (button_rect.height() - icon_size) // 2,
                icon_size,
                icon_size
            )
            text_rect = QRect(
                icon_rect.right() + 5,
                button_rect.top(),
                button_rect.width() - icon_rect.width() - 20,
                button_rect.height()
            )

            # 繪製圖示
            icon_func(self, painter, icon_rect)

            # 繪製文字
            painter.setPen(text_color)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

        # 依序繪製三個按鈕
        draw_button_with_icon(self.region_button_rect, ScreenshotOverlay.draw_region_icon, "區域截圖")
        draw_button_with_icon(self.window_button_rect, ScreenshotOverlay.draw_window_icon, "視窗截圖")
        draw_button_with_icon(self.fullscreen_button_rect, ScreenshotOverlay.draw_fullscreen_icon, "全螢幕截圖")
        
        # 繪製右邊的 ESC 提示文字
        painter.setPen(text_color)  # 使用與按鈕文字相同的白色
        # 使用與按鈕相同的字體設定
        esc_font = self.font()
        esc_font.setFamily("Microsoft JhengHei UI")
        esc_font.setPointSize(16)
        painter.setFont(esc_font)
        painter.drawText(self.esc_text_rect, Qt.AlignmentFlag.AlignCenter, "按下 ESC 退出畫面")
    
    def draw_region_icon(self, painter, rect):
        """繪製區域截圖圖示 (虛線框)"""
        painter.save()
        pen = QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        # 為了美觀，稍微內縮
        icon_rect = QRectF(rect).adjusted(4, 4, -4, -4)
        painter.drawRect(icon_rect)
        painter.restore()

    def draw_window_icon(self, painter, rect):
        """繪製視窗截圖圖示 (帶標題列的視窗)"""
        painter.save()
        pen = QPen(Qt.GlobalColor.white, 2)
        painter.setPen(pen)
        icon_rect = QRectF(rect).adjusted(4, 4, -4, -4)
        
        # 繪製視窗外框
        painter.drawRect(icon_rect)
        
        # 繪製標題列
        title_bar_height = icon_rect.height() / 3.5
        title_bar_rect = QRectF(icon_rect.topLeft(), QPointF(icon_rect.right(), icon_rect.top() + title_bar_height))
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(title_bar_rect)
        
        painter.restore()

    def draw_fullscreen_icon(self, painter, rect):
        """繪製全螢幕截圖圖示 (帶角落標記的實線框)"""
        painter.save()
        pen = QPen(Qt.GlobalColor.white, 2)
        painter.setPen(pen)
        icon_rect = QRectF(rect).adjusted(4, 4, -4, -4)
        
        # 繪製外框
        painter.drawRect(icon_rect)
        
        # 繪製四個角落的 L 型標記
        corner_length = 6
        # 左上
        painter.drawLine(icon_rect.topLeft(), icon_rect.topLeft() + QPointF(corner_length, 0))
        painter.drawLine(icon_rect.topLeft(), icon_rect.topLeft() + QPointF(0, corner_length))
        # 右上
        painter.drawLine(icon_rect.topRight(), icon_rect.topRight() - QPointF(corner_length, 0))
        painter.drawLine(icon_rect.topRight(), icon_rect.topRight() + QPointF(0, corner_length))
        # 左下
        painter.drawLine(icon_rect.bottomLeft(), icon_rect.bottomLeft() + QPointF(corner_length, 0))
        painter.drawLine(icon_rect.bottomLeft(), icon_rect.bottomLeft() - QPointF(0, corner_length))
        # 右下
        painter.drawLine(icon_rect.bottomRight(), icon_rect.bottomRight() - QPointF(corner_length, 0))
        painter.drawLine(icon_rect.bottomRight(), icon_rect.bottomRight() - QPointF(0, corner_length))
        
        painter.restore()

    def draw_screenshot_icon(self, painter, rect, color):
        """繪製螢幕截圖圖示"""
        # 設定繪製參數
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # 計算圖示中心和尺寸
        center_x = rect.center().x()
        center_y = rect.center().y()
        size = min(rect.width(), rect.height()) - 6
        half_size = size // 2
        
        # 繪製螢幕外框（矩形）
        screen_rect = QRect(center_x - half_size, center_y - half_size, size, int(size * 0.75))
        painter.drawRect(screen_rect)
        
        # 繪製螢幕內容（虛線表示截圖區域）
        painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
        inner_margin = 4
        inner_rect = QRect(screen_rect.left() + inner_margin, screen_rect.top() + inner_margin,
                          screen_rect.width() - inner_margin * 2, screen_rect.height() - inner_margin * 2)
        painter.drawRect(inner_rect)
        
        # 繪製選取框角落標記（表示截圖選取）Zimage.png
        painter.setPen(QPen(QColor("#00FF00"), 2))  # 綠色選取框
        corner_size = 6
        corners = [
            # 左上角
            (inner_rect.left(), inner_rect.top(), inner_rect.left() + corner_size, inner_rect.top()),
            (inner_rect.left(), inner_rect.top(), inner_rect.left(), inner_rect.top() + corner_size),
            # 右上角
            (inner_rect.right() - corner_size, inner_rect.top(), inner_rect.right(), inner_rect.top()),
            (inner_rect.right(), inner_rect.top(), inner_rect.right(), inner_rect.top() + corner_size),
            # 左下角
            (inner_rect.left(), inner_rect.bottom() - corner_size, inner_rect.left(), inner_rect.bottom()),
            (inner_rect.left(), inner_rect.bottom(), inner_rect.left() + corner_size, inner_rect.bottom()),
            # 右下角
            (inner_rect.right() - corner_size, inner_rect.bottom(), inner_rect.right(), inner_rect.bottom()),
            (inner_rect.right(), inner_rect.bottom() - corner_size, inner_rect.right(), inner_rect.bottom())
        ]
        
        for x1, y1, x2, y2 in corners:
            painter.drawLine(x1, y1, x2, y2)
        
        # 繪製閃光效果（表示截圖瞬間）
        painter.setPen(QPen(QColor("#FFFF99"), 1))  # 黃色閃光
        flash_lines = [
            (screen_rect.right() + 2, screen_rect.top() + 3, screen_rect.right() + 6, screen_rect.top() - 1),
            (screen_rect.right() + 2, screen_rect.top() + 8, screen_rect.right() + 8, screen_rect.top() + 8),
            (screen_rect.right() + 2, screen_rect.top() + 13, screen_rect.right() + 6, screen_rect.top() + 17)
        ]
        for x1, y1, x2, y2 in flash_lines:
            painter.drawLine(x1, y1, x2, y2)

    def mousePressEvent(self, event):
        if self.mode_selection_active:
            pos = event.pos()
            if self.fullscreen_button_rect.contains(pos):
                self.capture_fullscreen()
            elif self.region_button_rect.contains(pos):
                logging.info("模式: 區域截圖")
                self.capture_mode = 'region'
                self.mode_selection_active = False
                self.update() # 隱藏工具列
            elif self.window_button_rect.contains(pos):
                logging.info("模式: 視窗截圖")
                self.capture_mode = 'window'
                self.mode_selection_active = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.grabMouse() # 抓住滑鼠輸入，防止與下方視窗互動
                self.mouse_grabbed = True # 標記滑鼠已被抓住
                # 確保在抓住滑鼠後仍保持鍵盤焦點
                self.activateWindow()
                self.setFocus(Qt.FocusReason.OtherFocusReason)
                self.update() # 隱藏工具列
            # 點擊工具列外區域等同於選擇區域截圖
            elif not self.toolbar_rect.contains(pos):
                 self.capture_mode = 'region'
                 self.mode_selection_active = False
                 self.start_selection(event) # 立即開始選擇
        
        # 模式選擇完成後的點擊事件
        else:
            if self.capture_mode == 'region':
                self.start_selection(event)
            elif self.capture_mode == 'window':
                if self.highlighted_window_hwnd:
                    logging.info(f"準備擷取高亮視窗: HWND={self.highlighted_window_hwnd}")
                    self.capture_active_window()
                else:
                    logging.warning("在無效區域點擊，取消截圖。")
                    self.close() # close() 會呼叫 closeEvent 來釋放滑鼠

    def start_selection(self, event):
        """開始區域選擇的邏輯"""
        self.is_selecting = True
        self.start_point = event.globalPosition().toPoint()
        self.selection_rect = QRect()
        self.update() # 重新繪製以移除工具列

    def mouseMoveEvent(self, event):
        if self.is_clicking: # 如果已經在處理點擊，則忽略移動事件
            return
            
        # --- 新增：詳細的滑鼠座標日誌 ---
        physical_pos = event.globalPosition().toPoint()
        logical_pos = event.position().toPoint()
        logging.debug(f"滑鼠移動 - 實體 (Global): {physical_pos.x()},{physical_pos.y()} | 邏輯 (Local): {logical_pos.x()},{logical_pos.y()}")
        
        # --- 新增：根據滑鼠位置動態調整游標樣式 ---
        if self.mode_selection_active and self.toolbar_rect.contains(logical_pos):
            # 滑鼠在工具列上時，使用箭頭游標
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            # 滑鼠在其他區域時，根據模式設定游標
            if self.capture_mode == 'window':
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:  # 'region' 模式或尚未選擇模式
                self.setCursor(Qt.CursorShape.CrossCursor)
            
        if self.capture_mode == 'window':
            self.detect_window_under_cursor(event)
        elif self.capture_mode == 'region':
            if self.is_selecting:
                self.end_point = event.globalPosition().toPoint()
                # 將螢幕座標轉換為視窗內的相對座標
                local_start = self.mapFromGlobal(self.start_point)
                local_end = self.mapFromGlobal(self.end_point)
                self.selection_rect = QRect(local_start, local_end).normalized()
                self.update()

    def detect_window_under_cursor(self, event):
        """偵測滑鼠下方的視窗，支援子視窗且更精確"""
        if not win32gui or self.own_hwnd is None:
            return

        try:
            physical_pos = win32gui.GetCursorPos()
            mouse_x, mouse_y = physical_pos
            
            # 從 Z-Order 的最頂層開始往下找
            hwnd = win32gui.GetTopWindow(0)
            target_hwnd = None

            while hwnd:
                # 跳過我們自己的覆蓋層，以及任何隱藏或禁用的視窗
                if hwnd == self.own_hwnd or not win32gui.IsWindowVisible(hwnd) or not win32gui.IsWindowEnabled(hwnd):
                    hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)
                    continue

                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    # 檢查滑鼠是否在視窗範圍內
                    if rect[0] <= mouse_x < rect[2] and rect[1] <= mouse_y < rect[3]:
                        # 找到了！這是滑鼠下方最頂層的可見視窗
                        target_hwnd = hwnd
                        break # 找到後就停止搜索
                except Exception:
                    # 忽略那些無法獲取矩形的視窗 (例如某些系統元件)
                    pass

                hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)

            # 只有在偵測到的視窗發生變化時才更新，以提高效能
            if target_hwnd != self.highlighted_window_hwnd:
                self.highlighted_window_hwnd = target_hwnd
                self.last_hwnd = target_hwnd # 同步更新

                if target_hwnd:
                    target_rect = win32gui.GetWindowRect(target_hwnd)
                    screen = QApplication.screenAt(event.globalPosition().toPoint())
                    ratio = screen.devicePixelRatio() if screen else 1.0
                    if not ratio or ratio == 0: ratio = 1.0
                    
                    self.highlighted_window_geom = target_rect
                    self.highlighted_window_ratio = ratio
                else:
                    # 如果沒有偵測到視窗，清除高亮
                    self.highlighted_window_geom = None
                    self.highlighted_window_ratio = 1.0
                
                self.update() # 觸發重繪
                
        except Exception as e:
            logging.error(f"視窗偵測時發生錯誤: {e}", exc_info=True)

    def mouseReleaseEvent(self, event):
        if not self.is_selecting or self.capture_mode != 'region':
            return
        
        self.is_selecting = False
        
        # 檢查選取區域是否有效
        if self.selection_rect.width() > 5 and self.selection_rect.height() > 5:
            # 裁切圖片
            # QRect 座標是相對於視窗的，可以直接用於裁切 PIL 圖片
            cropped_image = self.full_screenshot.crop((
                self.selection_rect.left(),
                self.selection_rect.top(),
                self.selection_rect.right(),
                self.selection_rect.bottom()
            ))
            self.screenshot_taken.emit(cropped_image)
        
        self.close() # 無論如何都關閉視窗

    def closeEvent(self, event):
        """當視窗關閉時，釋放滑鼠抓住並清理 ESC 監聽器。"""
        # 清理 ESC 監聽器
        self._cleanup_esc_listener()
        
        # 釋放滑鼠抓住
        if self.mouse_grabbed:
            try:
                self.releaseMouse()
                self.mouse_grabbed = False
                logging.debug("已釋放滑鼠抓住")
            except RuntimeError:
                # 如果沒有抓住滑鼠，會拋出 RuntimeError，這是正常的
                logging.debug("嘗試釋放滑鼠時發生 RuntimeError（正常）")
                pass
        super().closeEvent(event)

    def capture_active_window(self):
        """
        擷取高亮視窗的內容。
        優先使用 PrintWindow API 以獲取被遮擋的內容，如果失敗則退回為裁切螢幕截圖。
        """
        if not self.highlighted_window_hwnd or not win32ui or not windll:
            logging.warning("擷取視窗內容所需模組不全或未選定視窗，退回為裁切模式。")
            self._capture_window_from_screenshot_crop()
            return

        hwnd = self.highlighted_window_hwnd
        logging.info(f"嘗試使用 PrintWindow API 擷取 HWND: {hwnd} 的內容。")

        try:
            # Vista+ (Windows 7/8/10/11) flag to capture layered windows.
            # Use 0 for older OSes.
            PW_RENDERFULLCONTENT = 0x00000002

            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top

            if width <= 0 or height <= 0:
                logging.warning(f"視窗 {hwnd} 的尺寸無效 ({width}x{height})，退回為裁切模式。")
                self._capture_window_from_screenshot_crop()
                return

            hwndDC = win32gui.GetWindowDC(hwnd)
            if not hwndDC: raise ValueError("無法獲取視窗的 Device Context (DC)。")
            
            mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            # 使用 PrintWindow 擷取視窗內容，1 表示成功
            result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT)

            image = None
            if result == 1:
                logging.info(f"PrintWindow 成功擷取 HWND: {hwnd}。")
                bmpinfo = saveBitMap.GetInfo()
                bmpstr = saveBitMap.GetBitmapBits(True)
                image = Image.frombuffer(
                    'RGB',
                    (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                    bmpstr, 'raw', 'BGRX', 0, 1)
            else:
                logging.warning(f"PrintWindow 擷取 HWND: {hwnd} 失敗，返回值: {result}。退回為裁切模式。")

            # 清理 GDI 物件
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)

            if image:
                self.screenshot_taken.emit(image)
                self.close()
            else:
                self._capture_window_from_screenshot_crop()

        except Exception as e:
            logging.error(f"使用 PrintWindow 擷取 HWND {hwnd} 時發生錯誤: {e}", exc_info=True)
            logging.info("退回為螢幕裁切模式。")
            self._capture_window_from_screenshot_crop()

    def _capture_window_from_screenshot_crop(self):
        """(備用方法) 擷取高亮的視窗區域 (從螢幕截圖中裁切)"""
        if self.highlighted_window_geom and self.full_screenshot:
            logging.info(f"執行視窗裁切，範圍: {self.highlighted_window_geom}")
            left, top, right, bottom = self.highlighted_window_geom

            # 裁切圖片。座標是全域的，需要相對於 full_screenshot 的左上角
            # self.full_screenshot 是從 virtual_screen 的左上角開始的
            crop_x = left - self.virtual_screen_rect.left()
            crop_y = top - self.virtual_screen_rect.top()
            crop_width = right - left
            crop_height = bottom - top

            cropped_image = self.full_screenshot.crop((
                crop_x,
                crop_y,
                crop_x + crop_width,
                crop_y + crop_height
            ))
            self.screenshot_taken.emit(cropped_image)
        self.close()

    def capture_fullscreen(self):
        """擷取全螢幕並發送信號"""
        if self.full_screenshot:
            self.screenshot_taken.emit(self.full_screenshot)
        self.close()

    def keyPressEvent(self, event):
        """按下 ESC 鍵取消，按下 Enter 鍵全螢幕截圖"""
        key_name = event.text() or f"Key_{event.key()}"
        logging.info(f"🔍 keyPressEvent 觸發: {key_name} (模式選擇中: {self.mode_selection_active}, 視窗焦點: {self.hasFocus()}, 視窗活動: {self.isActiveWindow()})")
        
        if event.key() == Qt.Key.Key_Escape:
            logging.info("✓ 使用者按下 ESC，取消截圖。")
            self.close()
        elif event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            logging.info("✓ 使用者按下 Enter，執行全螢幕截圖。")
            self.capture_fullscreen()
        else:
            logging.debug(f"其他按鍵: {key_name}")
            # 呼叫父類別的 keyPressEvent 以處理其他按鍵
            super().keyPressEvent(event)

# =============================================================================
# --- Global Hotkey Listener ---
# =============================================================================

class GlobalHotkeyListener(QObject):
    """在背景執行緒中監聽全域熱鍵的 Worker"""
    hotkey_triggered = pyqtSignal()
    
    def __init__(self, hotkey):
        super().__init__()
        self._running = True
        self._hotkey = hotkey
        self._trigger_event = threading.Event()

    def run(self):
        """此方法在 QThread 中執行"""
        logging.info(f"[{threading.current_thread().name}] Starting global hotkey listener for '{self._hotkey}'...")
        
        # 註冊熱鍵
        try:
            keyboard.add_hotkey(self._hotkey, self._on_hotkey_detected)
        except Exception as e:
            logging.error(f"✗ Failed to register hotkey '{self._hotkey}': {e}", exc_info=True)
            return

        # 保持執行緒活躍，直到被 stop()
        while self._running:
            # 使用 Event.wait() 來避免 CPU 忙碌等待
            # 如果事件被設置，等待1秒；否則一直等待
            if self._trigger_event.wait(1):
                if self._running: # 再次檢查狀態
                    self.hotkey_triggered.emit()
                self._trigger_event.clear() # 清除事件以便下次觸發

        # 清理
        try:
            keyboard.remove_hotkey(self._hotkey)
            logging.info(f"✓ Successfully removed hotkey: {self._hotkey}")
        except KeyError:
            pass # 可能熱鍵註冊失敗或已被移除
        except Exception as e:
            logging.error(f"✗ Error removing hotkey '{self._hotkey}': {e}", exc_info=True)
            
        logging.info(f"[{threading.current_thread().name}] Global hotkey listener stopped.")

    def _on_hotkey_detected(self):
        """由 'keyboard' 模組在內部執行緒中呼叫"""
        # 不要在此直接 emit signal，因為這不是 QThread 的主執行緒
        # 而是設置一個事件，讓 run() 迴圈來處理
        self._trigger_event.set()

    def stop(self):
        """從主執行緒呼叫此方法以停止監聽"""
        self._running = False
        # 喚醒等待中的 run() 迴圈，以便它能檢查 _running 狀態並退出
        self._trigger_event.set()

class GlobalEscListener(QObject):
    """專門監聽 ESC 鍵的全域監聽器"""
    esc_pressed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._running = True
        self._trigger_event = threading.Event()

    def run(self):
        """此方法在 QThread 中執行"""
        logging.info(f"[{threading.current_thread().name}] Starting global ESC listener...")
        
        # 註冊 ESC 鍵
        try:
            keyboard.add_hotkey('esc', self._on_esc_detected)
        except Exception as e:
            logging.error(f"✗ Failed to register ESC hotkey: {e}", exc_info=True)
            return

        # 保持執行緒活躍，直到被 stop()
        while self._running:
            if self._trigger_event.wait(1):
                if self._running:
                    self.esc_pressed.emit()
                self._trigger_event.clear()

        # 清理
        try:
            keyboard.remove_hotkey('esc')
            logging.info("✓ Successfully removed ESC hotkey")
        except KeyError:
            pass
        except Exception as e:
            logging.error(f"✗ Error removing ESC hotkey: {e}", exc_info=True)
            
        logging.info(f"[{threading.current_thread().name}] Global ESC listener stopped.")

    def _on_esc_detected(self):
        """當 ESC 鍵被按下時觸發"""
        self._trigger_event.set()

    def stop(self):
        """停止監聽"""
        self._running = False
        self._trigger_event.set()


# =============================================================================
# --- Pinned Screenshot Window ---
# =============================================================================

class PinnedScreenshotWindow(QWidget):
    """一個用於顯示、移動和操作已截取圖片的釘選視窗"""
    closed = pyqtSignal(object)

    def __init__(self, pil_image, main_tool_ref):
        super().__init__()
        self.pil_image = pil_image
        self.main_tool_ref = main_tool_ref
        self.drag_position = None
        
        # --- 新增：用於調整大小的屬性 ---
        self.resizing = False
        self.resize_edge = None
        self.resize_margin = 5

        # --- 將 PIL Image 轉換為 QPixmap ---
        im_rgba = self.pil_image.convert("RGBA")
        qimage = QImage(im_rgba.tobytes("raw", "RGBA"), im_rgba.width, im_rgba.height, QImage.Format.Format_RGBA8888)
        self.pixmap = QPixmap.fromImage(qimage)

        # --- 視窗設定 ---
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        # --- 設定視窗大小 ---
        toolbar_height = 40
        # self.setFixedSize(self.pixmap.width(), self.pixmap.height() + toolbar_height) # 移除固定大小
        self.resize(self.pixmap.width(), self.pixmap.height() + toolbar_height) # 設定初始大小
        self.setMinimumSize(200, 150) # 設定最小尺寸
        self.setMouseTracking(True) # 啟用滑鼠追蹤以更新游標

        # --- 佈局 ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 圖片顯示區域 ---
        self.image_label = QLabel()
        self.image_label.setPixmap(self.pixmap)
        self.image_label.setScaledContents(True) # 讓圖片可以縮放
        self.image_label.setMouseTracking(True) # 新增：啟用滑鼠追蹤
        main_layout.addWidget(self.image_label)

        # --- 自訂工具列 ---
        self.toolbar = QWidget()
        self.toolbar.setFixedHeight(toolbar_height)
        self.toolbar.setStyleSheet("background-color: #333;")
        self.toolbar.setMouseTracking(True) # 新增：啟用滑鼠追蹤
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(10, 0, 10, 0)
        
        copy_button = QPushButton("複製並關閉")
        copy_button.setStyleSheet("color: white; background-color: #007ACC; border: none; padding: 8px;")
        copy_button.clicked.connect(self.copy_and_close)
        
        close_button = QPushButton("關閉")
        close_button.setStyleSheet("color: white; background-color: #555; border: none; padding: 8px;")
        close_button.clicked.connect(self.close)

        toolbar_layout.addStretch()
        toolbar_layout.addWidget(copy_button)
        toolbar_layout.addWidget(close_button)
        
        main_layout.addWidget(self.toolbar)
        
        # --- 安裝事件過濾器以攔截子元件的滑鼠事件 ---
        self.image_label.installEventFilter(self)
        self.toolbar.installEventFilter(self)

        # --- 陰影效果 ---
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

    def eventFilter(self, watched, event):
        """
        事件過濾器，用於攔截 image_label 和 toolbar 的滑鼠事件，
        以便在整個視窗範圍內實現拖動和縮放功能。
        """
        # 我們只關心 image_label 和 toolbar 上的滑鼠事件
        if watched in [self.image_label, self.toolbar]:
            # --- 滑鼠移動事件: 用於更新游標和處理拖動/縮放 ---
            if event.type() == QEvent.Type.MouseMove:
                # 將事件座標從子元件轉換為主視窗(self)的座標
                local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
                remapped_event = QMouseEvent(
                    event.type(), local_pos, event.globalPosition(),
                    event.button(), event.buttons(), event.modifiers()
                )
                # 手動呼叫主視窗的 mouseMoveEvent
                self.mouseMoveEvent(remapped_event)
                return True # 事件已處理

            # --- 滑鼠按下事件: 用於開始拖動/縮放 ---
            if event.type() == QEvent.Type.MouseButtonPress:
                local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
                remapped_event = QMouseEvent(
                    event.type(), local_pos, event.globalPosition(),
                    event.button(), event.buttons(), event.modifiers()
                )
                self.mousePressEvent(remapped_event)
                # 任何在子元件上的點擊都應該被攔截並由主視窗處理，
                # 以啟動拖動或縮放。如果事件是按鈕點擊，
                # mousePressEvent 內部邏輯會因為不在邊緣而忽略它，
                # 並且 Qt 會將事件繼續傳遞給按鈕。
                # 我們返回 True 以表示我們已經處理了這個事件的拖動/縮放部分。
                return True

            # --- 滑鼠釋放事件: 用於結束拖動/縮放 ---
            if event.type() == QEvent.Type.MouseButtonRelease:
                local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
                remapped_event = QMouseEvent(
                    event.type(), local_pos, event.globalPosition(),
                    event.button(), event.buttons(), event.modifiers()
                )
                self.mouseReleaseEvent(remapped_event)
                return True # 總是處理釋放事件以結束操作

        # 對於其他所有事件，使用預設行為
        return super().eventFilter(watched, event)

    def copy_and_close(self):
        """將圖片複製到剪貼簿並關閉視窗"""
        try:
            self.main_tool_ref.set_clipboard_image(self.pil_image)
            self.main_tool_ref.show_custom_notification("成功", "釘選的圖片已複製到剪貼簿。", "success")
        except Exception as e:
            logging.error(f"從釘選視窗複製圖片時出錯: {e}", exc_info=True)
            self.main_tool_ref.show_custom_notification("失敗", f"複製圖片時發生錯誤:\n{e}", "warning")
        self.close()

    def get_resize_edges(self, pos):
        """根據滑鼠位置判斷在哪個邊緣或角落"""
        edges = []
        margin = self.resize_margin
        # 水平方向
        if 0 <= pos.x() < margin:
            edges.append(Qt.Edge.LeftEdge)
        elif self.width() - margin < pos.x() <= self.width():
            edges.append(Qt.Edge.RightEdge)
        # 垂直方向
        if 0 <= pos.y() < margin:
            edges.append(Qt.Edge.TopEdge)
        elif self.height() - margin < pos.y() <= self.height():
            edges.append(Qt.Edge.BottomEdge)
        return edges

    def update_cursor(self, pos):
        """根據滑鼠位置更新游標形狀"""
        edges = self.get_resize_edges(pos)
        if (Qt.Edge.TopEdge in edges and Qt.Edge.LeftEdge in edges) or \
           (Qt.Edge.BottomEdge in edges and Qt.Edge.RightEdge in edges):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif (Qt.Edge.TopEdge in edges and Qt.Edge.RightEdge in edges) or \
             (Qt.Edge.BottomEdge in edges and Qt.Edge.LeftEdge in edges):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif Qt.Edge.LeftEdge in edges or Qt.Edge.RightEdge in edges:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif Qt.Edge.TopEdge in edges or Qt.Edge.BottomEdge in edges:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.resize_edge = self.get_resize_edges(event.pos())
            if self.resize_edge:
                self.resizing = True
                self.resize_start_pos = event.globalPosition().toPoint()
                self.resize_start_geom = self.geometry()
            else:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.resizing:
            delta = event.globalPosition().toPoint() - self.resize_start_pos
            geom = QRect(self.resize_start_geom)

            if Qt.Edge.TopEdge in self.resize_edge:
                geom.setTop(self.resize_start_geom.top() + delta.y())
            if Qt.Edge.BottomEdge in self.resize_edge:
                geom.setBottom(self.resize_start_geom.bottom() + delta.y())
            if Qt.Edge.LeftEdge in self.resize_edge:
                geom.setLeft(self.resize_start_geom.left() + delta.x())
            if Qt.Edge.RightEdge in self.resize_edge:
                geom.setRight(self.resize_start_geom.right() + delta.x())

            # 檢查並修正最小尺寸
            if geom.height() < self.minimumHeight():
                if Qt.Edge.TopEdge in self.resize_edge:
                    geom.setTop(geom.bottom() - self.minimumHeight())
                else: # Bottom edge or no vertical resize
                    geom.setBottom(geom.top() + self.minimumHeight())
            
            if geom.width() < self.minimumWidth():
                if Qt.Edge.LeftEdge in self.resize_edge:
                    geom.setLeft(geom.right() - self.minimumWidth())
                else: # Right edge or no horizontal resize
                    geom.setRight(geom.left() + self.minimumWidth())

            self.setGeometry(geom)

        elif self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
        else:
            # 只有在沒有拖動或縮放時才更新游標
            self.update_cursor(event.pos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        self.resizing = False
        self.resize_edge = None
        self.update_cursor(event.pos()) # 確保釋放後游標正確
        event.accept()
        
    def closeEvent(self, event):
        """當視窗關閉時，發出信號通知主程式"""
        self.closed.emit(self)
        super().closeEvent(event)


# =============================================================================
# --- Main Application Class ---
# =============================================================================
class WatermarkToolQt(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.running = True
        self.overlay = None # 確保 overlay 只有一個實例
        self.current_notification = None # 追蹤目前的通知
        
        # --- Default Settings ---
        self.watermark_text = "© Fullbloom"
        self.font_size = 25
        self.opacity = 128
        self.watermark_style = "bottom_right"
        self.hotkey = "win+shift+z"
        self.show_notifications = True
        self.notification_duration_ms = 1000
        self.pin_screenshot_enabled = False # 新增：釘選截圖功能開關
        self.auto_save_enabled = False # 新增：自動儲存功能開關
        self.save_folder_path = os.path.join(os.path.expanduser("~"), "Desktop") # 新增：預設儲存路徑

        # --- 新增：追蹤釘選的視窗 ---
        self.pinned_windows = []

        # --- Paths ---
        appdata_path = os.getenv('LOCALAPPDATA')
        self.install_dir = os.path.join(appdata_path, "WatermarkTool")
        self.config_path = os.path.join(self.install_dir, "config.json")

        # --- Load Config on Startup ---
        self.load_config()
        
        logging.info("=" * 60)
        logging.info(" 自動浮水印截圖工具 - PyQt6 版本")
        logging.info("=" * 60)
        logging.info("程式已啟動！")
        logging.info(f"• 按 {self.hotkey.upper()} 啟動截圖工具")
        logging.info(f"安裝路徑: {self.install_dir}")
        logging.info("=" * 60)
        
        # --- Create Tray Icon ---
        self.tray_icon = None
        self.create_tray_icon()

        # --- Setup Global Hotkey Listener ---
        self.hotkey_thread = None
        self.hotkey_listener = None
        self.setup_hotkey_listener()
        
    def load_config(self):
        """從 config.json 檔案載入設定 (與原版相同)"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.watermark_text = config.get('watermark_text', self.watermark_text)
                    self.font_size = config.get('font_size', self.font_size)
                    self.opacity = config.get('opacity', self.opacity)
                    self.watermark_style = config.get('watermark_style', self.watermark_style)
                    self.hotkey = config.get('hotkey', 'win+shift+z')
                    self.show_notifications = config.get('show_notifications', True)
                    self.notification_duration_ms = config.get('notification_duration_ms', 1000)
                    self.pin_screenshot_enabled = config.get('pin_screenshot_enabled', False) # 新增
                    self.auto_save_enabled = config.get('auto_save_enabled', False) # 新增
                    self.save_folder_path = config.get('save_folder_path', os.path.join(os.path.expanduser("~"), "Desktop")) # 新增
                    logging.info(f"✓ 已從設定檔載入設定。目前樣式: {self.watermark_style}")
        except Exception as e:
            logging.error(f"✗ 載入設定檔失敗: {e}。將使用預設值。", exc_info=True)

    def save_config(self):
        """將目前設定儲存到 config.json 檔案 (與原版相同)"""
        try:
            os.makedirs(self.install_dir, exist_ok=True)
            config = {
                'watermark_text': self.watermark_text,
                'font_size': self.font_size,
                'opacity': self.opacity,
                'watermark_style': self.watermark_style,
                'hotkey': self.hotkey,
                'show_notifications': self.show_notifications,
                'notification_duration_ms': self.notification_duration_ms,
                'pin_screenshot_enabled': self.pin_screenshot_enabled, # 新增
                'auto_save_enabled': self.auto_save_enabled, # 新增
                'save_folder_path': self.save_folder_path # 新增
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            logging.info(f"✓ 設定已儲存。")
        except Exception as e:
            logging.error(f"✗ 儲存設定檔失敗: {e}", exc_info=True)
            
    def _create_icon_pixmap(self):
        """使用 PIL 創建圖示並轉換為 QIcon (與原版邏輯相同)"""
        image = Image.new('RGB', (64, 64), color='white')
        draw = ImageDraw.Draw(image)
        draw.rectangle([8, 8, 56, 56], outline='blue', width=6)
        draw.text((18, 16), "W", fill='blue', font=ImageFont.truetype("arialbd.ttf", 32))

        # Convert PIL image to QIcon
        from PyQt6.QtGui import QPixmap, QImage
        
        # Convert PIL image to QImage
        im_rgba = image.convert("RGBA")
        qimage = QImage(im_rgba.tobytes("raw", "RGBA"), im_rgba.width, im_rgba.height, QImage.Format.Format_RGBA8888)
        
        # Create a QPixmap from the QImage
        pixmap = QPixmap.fromImage(qimage)
        
        return QIcon(pixmap)


    def create_tray_icon(self):
        """使用 PyQt6 的 QSystemTrayIcon 創建系統托盤圖標"""
        self.tray_icon = QSystemTrayIcon(self._create_icon_pixmap(), self.app)
        self.tray_icon.setToolTip(f"截圖浮水印工具 (PyQt6) - {self.hotkey.upper()}")
        
        # --- Create Menu ---
        # 建立一個沒有父元件的主選單，它將被托盤圖示所擁有
        menu = QMenu()
        
        # Settings Action
        settings_action = QAction("設定浮水印", menu) # 父元件設為 menu
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)
        
        # Hotkey Settings Action
        hotkey_action = QAction("設定快捷鍵", menu) # 父元件設為 menu
        hotkey_action.triggered.connect(self.open_hotkey_settings)
        menu.addAction(hotkey_action)

        # --- Style Submenu ---
        style_menu = menu.addMenu("浮水印樣式") # 直接從主選單新增子選單
        
        style_group = QActionGroup(style_menu) # 父元件設為 style_menu
        style_group.setExclusive(True)
        
        styles = {
            "右下角": "bottom_right",
            "重複平鋪": "tiled",
            "置中": "center",
            "單一斜向": "diagonal"
        }
        
        for text, style_id in styles.items():
            action = QAction(text, style_menu, checkable=True) # 父元件設為 style_menu
            action.setChecked(self.watermark_style == style_id)
            action.triggered.connect(lambda checked, s=style_id: self.set_watermark_style(s))
            style_group.addAction(action)
            style_menu.addAction(action)
            
        menu.addSeparator()

        # Test Actions
        test_watermark_action = QAction("測試浮水印 (貼至剪貼簿)", menu) # 父元件設為 menu
        test_watermark_action.triggered.connect(self.test_watermark)
        menu.addAction(test_watermark_action)
        
        test_capture_action = QAction("測試多螢幕截圖", menu) # 父元件設為 menu
        test_capture_action.triggered.connect(self.test_multi_screen_capture_placeholder)
        menu.addAction(test_capture_action)
        
        menu.addSeparator()

        # --- 新增：釘選截圖功能 ---
        self.pin_action = QAction("釘選截圖於畫面上", menu, checkable=True)
        self.pin_action.setChecked(self.pin_screenshot_enabled)
        self.pin_action.triggered.connect(self.toggle_pin_screenshot)
        menu.addAction(self.pin_action)
        
        # --- 新增：自動儲存功能 ---
        self.auto_save_action = QAction("自動儲存圖片", menu, checkable=True)
        self.auto_save_action.setChecked(self.auto_save_enabled)
        self.auto_save_action.triggered.connect(self.toggle_auto_save)
        menu.addAction(self.auto_save_action)
        
        menu.addSeparator()
        
        # --- Startup Action ---
        self.startup_action = QAction("開機啟動", menu, checkable=True)
        self.startup_action.setChecked(self.is_startup_enabled())
        self.startup_action.triggered.connect(self.toggle_startup)
        menu.addAction(self.startup_action)

        # Quit Action
        quit_action = QAction("退出", menu) # 父元件設為 menu
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def set_watermark_style(self, style):
        logging.info(f"浮水印樣式已切換為: {style}")
        self.watermark_style = style
        self.save_config()
        # self.test_watermark_placeholder() # Optionally trigger a test
        
    def toggle_pin_screenshot(self, checked):
        """切換是否啟用釘選截圖功能"""
        self.pin_screenshot_enabled = checked
        logging.info(f"釘選截圖功能已 {'啟用' if checked else '關閉'}")
        self.save_config()
    
    def toggle_auto_save(self, checked):
        """切換是否啟用自動儲存功能"""
        self.auto_save_enabled = checked
        
        # 如果啟用自動儲存但沒有設定路徑，設定預設為桌面
        if checked and not self.save_folder_path:
            self.save_folder_path = os.path.join(os.path.expanduser("~"), "Desktop")
        
        logging.info(f"自動儲存功能已 {'啟用' if checked else '關閉'}")
        if checked:
            logging.info(f"儲存路徑: {self.save_folder_path}")
        self.save_config()

    def quit_application(self):
        logging.info("正在退出程式...")
        self.running = False
        if self.hotkey_thread and self.hotkey_thread.isRunning():
            logging.info("Stopping hotkey listener...")
            self.hotkey_listener.stop()
            self.hotkey_thread.quit()
            self.hotkey_thread.wait(1000)

        if self.tray_icon:
            self.tray_icon.hide()
        self.app.quit()

    # --- Placeholder Methods for UI actions ---
    # We will implement these in the next phases
    def open_settings(self):
        """開啟設定浮水印對話框"""
        current_settings = {
            'watermark_text': self.watermark_text,
            'font_size': self.font_size,
            'opacity': self.opacity,
            'show_notifications': self.show_notifications,
            'notification_duration_ms': self.notification_duration_ms,
            'auto_save_enabled': self.auto_save_enabled,
            'save_folder_path': self.save_folder_path
        }
        dialog = SettingsDialog(current_settings=current_settings)
        if dialog.exec():
            new_settings = dialog.get_settings()
            self.watermark_text = new_settings['watermark_text']
            self.font_size = new_settings['font_size']
            self.opacity = new_settings['opacity']
            self.show_notifications = new_settings['show_notifications']
            self.notification_duration_ms = new_settings['notification_duration_ms']
            self.auto_save_enabled = new_settings['auto_save_enabled']
            self.save_folder_path = new_settings['save_folder_path']
            
            # 更新托盤選單中的自動儲存選項狀態
            if hasattr(self, 'auto_save_action'):
                self.auto_save_action.setChecked(self.auto_save_enabled)
            
            self.save_config()
            logging.info("✓ 浮水印設定已更新。")
            self.show_custom_notification("設定完成", "浮水印設定已更新並儲存！", "success")

    def open_hotkey_settings(self):
        """開啟設定快捷鍵對話框"""
        dialog = HotkeyDialog(current_hotkey=self.hotkey)
        if dialog.exec() and dialog.new_hotkey:
            old_hotkey = self.hotkey
            self.hotkey = dialog.new_hotkey
            self.save_config()
            logging.info(f"✓ 快捷鍵已更新為: {self.hotkey.upper()}")
            # 動態更新熱鍵監聽器
            self.setup_hotkey_listener(old_hotkey=old_hotkey) 
            self.tray_icon.setToolTip(f"截圖浮水印工具 (PyQt6) - {self.hotkey.upper()}")
            self.show_custom_notification("成功", f"快捷鍵已成功更新為: {self.hotkey.upper()}", "success")

    def show_custom_notification(self, title, message, icon_type='info'):
        """
        顯示自訂的 Toast 通知。
        此函式經過特殊設計，可以處理快速連續呼叫的情況。
        """
        if not self.show_notifications:
            return

        # 如果已有通知正在顯示，先關閉它。
        # 它的 destroyed 信號會處理後續的記憶體清理。
        if self.current_notification:
            self.current_notification.close()

        # 建立一個新的通知實例
        notification = CustomNotification(
            title,
            message,
            icon_type,
            duration_ms=self.notification_duration_ms
        )
        
        # 將新的實例存為「目前的通知」
        self.current_notification = notification

        # --- 關鍵修正 ---
        # 為這個「特定的」通知實例設定一個清理回呼。
        # 使用 lambda 或是 closure 可以捕獲當前的 `notification` 變數。
        # 當這個通知被銷毀時，lambda 會被呼叫。
        # 它會檢查 `self.current_notification` 是否仍然是當初它自己。
        # 如果是，表示沒有更新的通知出現，此時可以安全地將其設為 None。
        # 如果不是，表示已經有新的通知取代了它，那麼就不做任何事，避免錯誤地清除了新通知的參考。
        notification.destroyed.connect(
            lambda: self._on_notification_destroyed(notification)
        )
        
        notification.show_notification()

    def _on_notification_destroyed(self, destroyed_notification):
        """當自訂通知視窗被銷毀時，有條件地清除對它的引用"""
        # 只有當被銷毀的通知仍然是我們記錄的當前通知時，才清除引用
        if self.current_notification is destroyed_notification:
            self.current_notification = None
            logging.debug("當前通知的引用已安全清除。")
        else:
            logging.debug("一個舊的通知已被銷毀，但不是當前通知，無需清除引用。")

    def test_watermark(self):
        """產生一張測試圖片，加上浮水印並複製到剪貼簿"""
        logging.info("\n產生測試圖片...")
        try:
            test_image = Image.new('RGB', (800, 600), color='lightblue')
            draw = ImageDraw.Draw(test_image)
            try:
                # 使用更易於閱讀的預設字體
                font = ImageFont.truetype("msjh.ttc", 30)
            except IOError:
                font = ImageFont.load_default()
            draw.text((50, 50), "這是 PyQt6 版本的測試圖片\nThis is a test image", fill='black', font=font)
            
            watermarked = self.add_watermark(test_image)
            self.set_clipboard_image(watermarked)
            logging.info("✓ 測試圖片已複製到剪貼簿。")
            self.show_custom_notification(
                "測試成功",
                "已產生一張測試圖片並複製到剪貼簿，請貼上查看效果。",
                "success"
            )
        except Exception as e:
            logging.error(f"✗ 測試浮水印失敗: {e}", exc_info=True)
            self.show_custom_notification(
                "測試失敗",
                f"產生測試圖片時發生錯誤:\n{e}",
                "warning"
            )

    def test_multi_screen_capture_placeholder(self):
        logging.info("佔位符: 測試多螢幕截圖...")
        QApplication.beep()
        self.show_custom_notification("提示", "此功能已被主要截圖流程取代。", "info")

    # --- Hotkey and Screenshot Logic ---
    def setup_hotkey_listener(self, old_hotkey=None):
        """設定或更新全域熱鍵監聽器"""
        # 1. 如果有舊的執行緒，先停止它
        if self.hotkey_thread and self.hotkey_thread.isRunning():
            logging.info(f"Stopping old hotkey listener for '{old_hotkey or self.hotkey}'...")
            self.hotkey_listener.stop()
            self.hotkey_thread.quit()
            self.hotkey_thread.wait(1000) # 等待執行緒結束
            logging.info("Old listener stopped.")
        
        # 2. 建立新的執行緒和 Worker
        self.hotkey_thread = QThread()
        self.hotkey_listener = GlobalHotkeyListener(self.hotkey)
        self.hotkey_listener.moveToThread(self.hotkey_thread)

        # 3. 連接信號與槽
        #    - 執行緒啟動時，執行 worker 的 run 方法
        #    - worker 發出 hotkey_triggered 信號時，呼叫主程式的 on_screenshot_hotkey
        #    - 執行緒結束時，可以做一些清理工作 (可選)
        self.hotkey_thread.started.connect(self.hotkey_listener.run)
        self.hotkey_listener.hotkey_triggered.connect(self.on_screenshot_hotkey)

        # 4. 啟動執行緒
        self.hotkey_thread.start()
        logging.info(f"✓ Global hotkey listener for '{self.hotkey.upper()}' is now active.")

    def on_screenshot_hotkey(self):
        """當全域熱鍵被觸發時執行的槽函數 (在主執行緒中)"""
        if self.overlay and self.overlay.isVisible():
            logging.warning("⚠️ 截圖已在進行中，忽略重複請求")
            return
            
        logging.info(f"\n✓ 偵測到 {self.hotkey.upper()}！啟動截圖模式...")
        
        # 延遲一小段時間確保按鍵已釋放
        # from PyQt6.QtCore import QTimer # 已移至檔案頂部
        timer = QTimer()
        timer.singleShot(200, self.show_screenshot_overlay)

    def show_screenshot_overlay(self):
        """顯示截圖覆蓋層"""
        logging.debug("show_screenshot_overlay - 準備顯示覆蓋層")
        self.overlay = ScreenshotOverlay()
        # 將截圖完成的信號連接到處理函數
        self.overlay.screenshot_taken.connect(self.process_screenshot)
        self.overlay.show() # 使用 show()，大小在 __init__ 中已設定
        
    def process_screenshot(self, captured_image):
        """處理截圖、加上浮水印並決定是釘選還是複製到剪貼簿"""
        logging.debug("process_screenshot - 開始")
        logging.info("✓ 截圖完成，正在加上浮水印...")
        try:
            watermarked_image = self.add_watermark(captured_image)
            
            # 自動儲存圖片（如果啟用）
            saved_path = None
            if self.auto_save_enabled:
                saved_path = self.auto_save_image(watermarked_image)
            
            # 根據設定決定後續動作
            if self.pin_screenshot_enabled:
                logging.info("📌 釘選模式已啟用，建立釘選視窗。")
                self.create_pinned_window(watermarked_image)
                
                # 如果同時啟用了自動儲存，顯示包含儲存資訊的通知
                if saved_path:
                    self.show_custom_notification(
                        "成功！",
                        f"截圖已釘選到畫面上，並已儲存至:\n{os.path.basename(saved_path)}",
                        "success"
                    )
            else:
                self.set_clipboard_image(watermarked_image)
                logging.info("✓ 加上浮水印的圖片已複製到剪貼簿。")
                
                # 根據是否有自動儲存顯示不同的通知訊息
                if saved_path:
                    self.show_custom_notification(
                        "成功！",
                        f"已擷取螢幕並加上浮水印，圖片已複製到剪貼簿並儲存至:\n{os.path.basename(saved_path)}",
                        "success"
                    )
                else:
                    self.show_custom_notification(
                        "成功！",
                        "已擷取螢幕並加上浮水印，圖片已複製到剪貼簿。",
                        "success"
                    )
                    
        except Exception as e:
            logging.error(f"✗ 處理截圖時發生錯誤: {e}", exc_info=True)
            self.show_custom_notification(
                "處理失敗",
                f"為圖片加上浮水印時發生錯誤:\n{e}",
                "warning"
            )
        logging.debug("process_screenshot - 結束")

    def create_pinned_window(self, image):
        """建立、顯示並追蹤一個新的釘選視窗"""
        pin_win = PinnedScreenshotWindow(image, self)
        pin_win.closed.connect(self.on_pinned_window_closed)
        self.pinned_windows.append(pin_win)
        pin_win.show()
        pin_win.activateWindow() # 確保新視窗獲得焦點
        pin_win.raise_()         # 將視窗提到最上層

    def on_pinned_window_closed(self, window_instance):
        """當一個釘選視窗關閉時，將其從追蹤列表中移除"""
        try:
            self.pinned_windows.remove(window_instance)
            logging.info(f"一個釘選視窗已關閉，目前剩餘 {len(self.pinned_windows)} 個。")
        except ValueError:
            logging.warning("嘗試移除一個不在追蹤列表中的釘選視窗。")
    
    def generate_filename(self):
        """產生唯一的檔案名稱"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"Screenshot_{timestamp}.png"
    
    def auto_save_image(self, image):
        """自動儲存圖片到指定資料夾"""
        if not self.auto_save_enabled or not self.save_folder_path:
            return None
            
        try:
            # 確保儲存資料夾存在
            os.makedirs(self.save_folder_path, exist_ok=True)
            
            # 產生唯一檔案名稱
            filename = self.generate_filename()
            filepath = os.path.join(self.save_folder_path, filename)
            
            # 如果檔案已存在，加上序號
            counter = 1
            base_name = filename.rsplit('.', 1)[0]
            extension = filename.rsplit('.', 1)[1]
            while os.path.exists(filepath):
                filename = f"{base_name}_{counter}.{extension}"
                filepath = os.path.join(self.save_folder_path, filename)
                counter += 1
            
            # 儲存圖片
            image.save(filepath, 'PNG')
            logging.info(f"✓ 圖片已自動儲存至: {filepath}")
            return filepath
            
        except Exception as e:
            logging.error(f"✗ 自動儲存圖片失敗: {e}", exc_info=True)
            return None

    # --- Startup Logic (Copied and adapted from original) ---

    def is_startup_enabled(self):
        """檢查程式是否已設定為開機啟動"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "WatermarkScreenshotTool")
            winreg.CloseKey(key)
            # 檢查路徑是否與安裝路徑一致
            if self.install_dir.lower() in value.lower():
                return True
            return False
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def cleanup_install_directory(self):
        """安全地清理安裝資料夾"""
        try:
            if os.path.exists(self.install_dir):
                logging.info(f"正在清理安裝資料夾: {self.install_dir}")
                shutil.rmtree(self.install_dir)
                logging.info("✓ 安裝資料夾已清理完成。")
                return True
        except Exception as e:
            logging.error(f"✗ 清理安裝資料夾時發生錯誤: {e}", exc_info=True)
            return False

    def toggle_startup(self):
        """設定或取消開機自動啟動"""
        app_name = "WatermarkScreenshotTool"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run", 0, winreg.KEY_ALL_ACCESS)
            if self.is_startup_enabled():
                # --- 取消開機啟動 ---
                winreg.DeleteValue(key, app_name)
                logging.info("✓ 已關閉開機啟動。")
                cleanup_success = self.cleanup_install_directory()
                if cleanup_success:
                    QMessageBox.information(None, "設定成功", "已取消開機自動啟動，並清理了安裝檔案。")
                else:
                    QMessageBox.warning(None, "部分成功", "已取消開機自動啟動，但清理安裝檔案時發生問題。\n\n您可以手動刪除以下資料夾:\n" + self.install_dir)
            else:
                # --- 設定開機啟動 ---
                logging.info("正在設定開機啟動並安裝程式...")
                os.makedirs(self.install_dir, exist_ok=True)
                
                source_path = os.path.abspath(sys.argv[0])
                dest_path = os.path.join(self.install_dir, os.path.basename(source_path))
                
                if source_path.lower() != dest_path.lower():
                    shutil.copy2(source_path, dest_path)
                
                # 使用 pythonw.exe 確保背景執行無黑窗
                python_exe = sys.executable
                if "pythonw.exe" in python_exe:
                    pythonw_path = python_exe
                else:
                    pythonw_path = python_exe.replace("python.exe", "pythonw.exe")

                command = f'"{pythonw_path}" "{dest_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
                
                QMessageBox.information(None, "設定成功", f"已成功設定開機啟動！\n\n程式已安裝至:\n{self.install_dir}\n\n您可以關閉此程式並刪除原始檔案。")
            
            winreg.CloseKey(key)
        except Exception as e:
            logging.error(f"設定開機啟動失敗: {e}", exc_info=True)
            QMessageBox.critical(None, "設定失敗", f"發生錯誤:\n{e}")
        
        # 最後，更新選單的勾選狀態
        if self.startup_action:
            self.startup_action.setChecked(self.is_startup_enabled())

    # --- Core Logic Methods (Copied from original) ---
    
    def set_clipboard_image(self, image):
        """將 PIL Image 物件複製到 Windows 剪貼簿 (與原版邏輯相同)"""
        try:
            output = BytesIO()
            image.convert("RGB").save(output, format='BMP')
            data = output.getvalue()[14:] # BMP 格式需要移除檔頭
            output.close()

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, data)
        except Exception as e:
            logging.error(f"✗ 設定剪貼簿失敗: {e}", exc_info=True)
        finally:
            try: win32clipboard.CloseClipboard()
            except: pass

    def _load_font(self):
        font_paths = ["msjh.ttc", "msjhl.ttc", "simhei.ttf", "arial.ttf"]
        for font_path in font_paths:
            try: return ImageFont.truetype(font_path, self.font_size)
            except IOError: continue
        return ImageFont.load_default(self.font_size)

    def add_watermark(self, image):
        image_copy = image.copy().convert('RGBA')
        font = self._load_font()
        style_map = {
            "bottom_right": self._add_watermark_bottom_right,
            "tiled": self._add_watermark_tiled,
            "center": self._add_watermark_center,
            "diagonal": self._add_watermark_diagonal
        }
        watermark_func = style_map.get(self.watermark_style)
        if not watermark_func:
            return image
        
        watermark_layer = watermark_func(image_copy.size, font)
        watermarked = Image.alpha_composite(image_copy, watermark_layer)
        background = Image.new('RGB', watermarked.size, (255, 255, 255))
        background.paste(watermarked, mask=watermarked.split()[-1])
        return background

    def _get_text_dimensions(self, font, text):
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _add_watermark_bottom_right(self, size, font):
        layer = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        text_width, text_height = self._get_text_dimensions(font, self.watermark_text)
        margin = 35
        x = size[0] - text_width - margin
        y = size[1] - text_height - margin
        draw.text((x, y), self.watermark_text, font=font, fill=(0, 0, 0, self.opacity))
        return layer

    def _add_watermark_center(self, size, font):
        layer = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        text_width, text_height = self._get_text_dimensions(font, self.watermark_text)
        x = (size[0] - text_width) / 2
        y = (size[1] - text_height) / 2
        draw.text((x, y), self.watermark_text, font=font, fill=(0, 0, 0, self.opacity))
        return layer

    def _add_watermark_diagonal(self, size, font):
        layer = Image.new('RGBA', size, (0, 0, 0, 0))
        text_width, text_height = self._get_text_dimensions(font, self.watermark_text)
        text_layer = Image.new('RGBA', (text_width, text_height), (0,0,0,0))
        draw_text = ImageDraw.Draw(text_layer)
        draw_text.text((0, 0), self.watermark_text, font=font, fill=(0, 0, 0, self.opacity))
        angle = -math.degrees(math.atan2(size[1], size[0]))
        rotated_text = text_layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        x = (size[0] - rotated_text.width) // 2
        y = (size[1] - rotated_text.height) // 2
        layer.paste(rotated_text, (x, y), rotated_text)
        return layer

    def _add_watermark_tiled(self, size, font):
        layer = Image.new('RGBA', size, (0, 0, 0, 0))
        text_width, text_height = self._get_text_dimensions(font, self.watermark_text)
        padding = 80
        tile_size = (text_width + padding, text_height + padding * 2)
        tile = Image.new('RGBA', tile_size, (0,0,0,0))
        draw_tile = ImageDraw.Draw(tile)
        draw_tile.text((padding / 2, padding), self.watermark_text, font=font, fill=(0, 0, 0, self.opacity))
        rotated_tile = tile.rotate(30, expand=True, resample=Image.Resampling.BICUBIC)
        spacing_x = rotated_tile.width + 100
        spacing_y = rotated_tile.height + 50
        for y in range(-rotated_tile.height, size[1] + rotated_tile.height, spacing_y):
            for x in range(-rotated_tile.width, size[0] + rotated_tile.width, spacing_x):
                layer.paste(rotated_tile, (x, y), rotated_tile)
        return layer

def log_uncaught_exceptions(ex_cls, ex, tb):
    """全域異常捕獲器"""
    text = ''.join(traceback.format_exception(ex_cls, ex, tb))
    logging.critical(f"捕獲到未處理的致命異常:\n{text}")
    # 也可以彈出一個對話框通知使用者

def setup_logging():
    """設定日誌記錄器，同時輸出到檔案和控制台"""
    log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'watermark_tool.log')
    
    # 基本設定，設定日誌等級和格式
    logging.basicConfig(
        level=logging.DEBUG, # 修改為 DEBUG 等級以記錄更多資訊
        format='%(asctime)s - %(levelname)s - [%(threadName)s:%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, 'w', 'utf-8'), # 寫入檔案
            logging.StreamHandler() # 輸出到控制台
        ]
    )
    logging.info("日誌系統已設定完成。")

def main():
    # Mutex for single instance (logic copied and adapted)
    mutex_name = "WatermarkScreenshotTool_Mutex_PyQt6_2025"
    try:
        import win32event, win32api, winerror
        mutex = win32event.CreateMutex(None, 1, mutex_name)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            # Use a simple tkinter messagebox for notification
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning("程式已在執行", "浮水印工具 (PyQt6 版) 已經在背景執行了。")
            root.destroy()
            sys.exit(0)
    except ImportError:
        logging.warning("提示：未安裝 pywin32，無法防止程式重複執行。")
    except Exception as e:
        logging.error(f"檢查程式實例時出錯: {e}", exc_info=True)

    # --- Main Application Setup ---
    # This ensures the application doesn't close when the last window is hidden.
    # --- 新增：設定高 DPI 感知 ---
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    # QApplication.setAttribute(Qt.AA_EnableHighDpiScaling) # <-- 此行在 PyQt6 中已棄用並導致錯誤，予以移除
    
    app = QApplication(sys.argv)
    QApplication.setQuitOnLastWindowClosed(False)
    
    # 將 tool 物件附加到 app 上，防止其被垃圾回收
    app.tool_instance = WatermarkToolQt(app)
    
    logging.info("Starting application event loop...")
    sys.exit(app.exec())


if __name__ == "__main__":
    # --- 新增：讓 Windows 知道此程式具備 DPI 感知能力 ---
    # 必須在任何 GUI 元件建立前呼叫
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        # 在舊版 Windows 上可能失敗，但程式仍可繼續執行
        logging.warning("無法設定 DPI 感知 (可能為舊版 Windows)，繼續執行...")
        
    setup_logging() # 在最一開始就設定日誌
    sys.excepthook = log_uncaught_exceptions # 設定全域異常捕獲
    try:
        main()
    except Exception as e:
        # --- 全域錯誤捕獲 ---
        # 如果應用程式在啟動時崩潰，將錯誤訊息顯示在一個彈出視窗中
        root = tk.Tk()
        root.withdraw()
        error_title = "應用程式發生嚴重錯誤"
        error_message = f"程式無法啟動，發生了未預期的錯誤。\n\n錯誤詳情:\n{type(e).__name__}: {e}\n\nTraceback:\n{traceback.format_exc()}"
        logging.critical(error_message) # 記錄嚴重錯誤
        messagebox.showerror(error_title, error_message)
        sys.exit(1)
