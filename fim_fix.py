import os
import sys
import hashlib
import json
import argparse
import shutil # Thư viện mới để copy/xóa file vật lý
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, simpledialog
from datetime import datetime

try:
    from plyer import notification
except ImportError:
    messagebox.showerror("Lỗi","Vui lòng cài đặt thư viện plyer: pip install plyer")
    sys.exit(1)

if sys.platform == "win32":
    import winreg

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

CONFIG_FILE = "fim_config.json"
SNAPSHOT_DIR = "snapshots"
BACKUP_DIR = os.path.join(SNAPSHOT_DIR, "files") # Kho chứa bản sao vật lý

class FIMEventHandler(FileSystemEventHandler):
    def __init__(self, app_instance):
        self.app = app_instance

    def on_created(self, event):
        if not event.is_directory:
            self.app.process_event('created', event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.app.process_event('modified', event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.app.process_event('deleted', event.src_path)

class FIMApplication:
    def __init__(self, root, is_startup=False):
        self.root = root
        self.root.title("FIM")
        self.root.geometry("750x600")
        self.root.resizable(True, True)
        
        self.observer = None
        self.live_state = {} # Key: Đường dẫn tương đối, Value: Mã Hash
        self.config = self.load_config()
        self.is_startup = is_startup

        # Khởi tạo môi trường và vẽ giao diện
        self.init_environment()
        self.build_gui()

        # Nếu mở app bằng tay (không qua startup), tự động check offline ngay
        if not self.is_startup:
            self.root.after(500, self.run_startup_check)

        if self.is_startup and self.config.get("target_dir"):
            self.root.iconify()
            self.root.after(1000, lambda: self.toggle_monitor(is_auto=True))

    def init_environment(self):
        if not os.path.exists(SNAPSHOT_DIR):
            os.makedirs(SNAPSHOT_DIR)
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"target_dir": "", "password_hash": ""}

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    def get_history_file(self):
        """Lấy file nhật ký riêng cho từng thư mục giám sát"""
        target_dir = self.config.get("target_dir", "")
        safe_name = target_dir.replace("\\", "_").replace("/", "_").replace(":", "")
        return os.path.join(SNAPSHOT_DIR, f"history_{safe_name}.json")

    def build_gui(self):
        # --- Frame 1: Cấu hình ---
        frame_top = ttk.LabelFrame(self.root, text="Cấu hình Theo dõi", padding=(10, 5))
        frame_top.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(frame_top, text="Thư mục:").grid(row=0, column=0, padx=5, pady=5)
        self.dir_var = tk.StringVar(value=self.config.get("target_dir", ""))
        self.entry_dir = ttk.Entry(frame_top, textvariable=self.dir_var, width=60, state='readonly')
        self.entry_dir.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(frame_top, text="Đổi Thư mục...", command=self.change_directory).grid(row=0, column=2, padx=5, pady=5)

        # --- Frame 2: Điều khiển ---
        frame_mid = ttk.Frame(self.root)
        frame_mid.pack(fill=tk.X, padx=10, pady=5)

        self.btn_monitor = ttk.Button(frame_mid, text="▶ BẮT ĐẦU GIÁM SÁT", command=self.toggle_monitor, width=25)
        self.btn_monitor.pack(side=tk.LEFT, padx=5)

        # NÚT MỚI: Khôi phục Trạng thái
        self.btn_restore = ttk.Button(frame_mid, text="⏮ KHÔI PHỤC TRẠNG THÁI", command=self.open_restore_window, width=25)
        self.btn_restore.pack(side=tk.LEFT, padx=5)

        if sys.platform == "win32":
            ttk.Button(frame_mid, text="⚙ Auto-Start", command=self.add_to_startup).pack(side=tk.RIGHT, padx=5)

        # --- Frame 3: Log ---
        frame_bot = ttk.LabelFrame(self.root, text="Giám sát Thời gian thực", padding=(10, 5))
        frame_bot.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.log_area = scrolledtext.ScrolledText(frame_bot, wrap=tk.WORD, state='disabled', bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10))
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.tag_config('info', foreground='#569cd6')
        self.log_area.tag_config('warning_mod', foreground='#d7ba7d')
        self.log_area.tag_config('warning_del', foreground='#f44747')
        self.log_area.tag_config('warning_add', foreground='#608b4e')

        self.write_log("Hệ thống khởi động thành công.", "info")

    # --- BẢO MẬT ---
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def authenticate(self, action_name):
        saved_hash = self.config.get("password_hash")
        if saved_hash:
            pwd = simpledialog.askstring("Xác thực Bảo mật", f"Nhập mật khẩu quản trị để {action_name}:", show='*')
            if not pwd or self.hash_password(pwd) != saved_hash:
                messagebox.showerror("Từ chối truy cập", "Mật khẩu không chính xác hoặc đã hủy!")
                return False
            return True
        else:
            msg = f"Tạo MẬT KHẨU QUẢN TRỊ để bảo vệ tính năng {action_name}:"
            pwd = simpledialog.askstring("Tạo mật khẩu", msg, show='*')
            if not pwd: return False 
            self.config["password_hash"] = self.hash_password(pwd)
            self.save_config()
            return True

    def change_directory(self):
        if self.observer is not None:
            messagebox.showwarning("Cảnh báo", "Hệ thống đang hoạt động!\nVui lòng DỪNG giám sát trước khi đổi thư mục.")
            return

        folder_selected = filedialog.askdirectory()
        if folder_selected:
            safe_path = folder_selected.replace("/", "\\")
            self.dir_var.set(safe_path)
            self.config["target_dir"] = safe_path
            self.save_config()
            self.write_log(f"Đã cập nhật thư mục giám sát mới: {safe_path}", "info")

    def add_to_startup(self):
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            exec_path = f'"{sys.executable}" "{os.path.abspath(__file__)}" --startup'
            winreg.SetValueEx(key, "FIM_Optimizer", 0, winreg.REG_SZ, exec_path)
            winreg.CloseKey(key)
            messagebox.showinfo("Thành công", "Đã thêm vào Registry!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi Registry: {e}")

    # --- LOGIC BACKUP & SNAPSHOT CHUYÊN SÂU ---
    def calculate_sha256(self, file_path):
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return None

    def backup_file(self, file_path, file_hash):
        """Copy file vật lý vào kho chứa (nếu chưa có)"""
        target_backup_path = os.path.join(BACKUP_DIR, file_hash)
        if not os.path.exists(target_backup_path):
            try:
                shutil.copy2(file_path, target_backup_path)
            except Exception as e:
                print(f"Lỗi sao lưu file: {e}")

    def record_snapshot(self, description):
        """Ghi lại trạng thái toàn bộ thư mục vào dòng thời gian"""
        history_file = self.get_history_file()
        history = []
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                try: history = json.load(f)
                except: pass

        snapshot = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": description,
            "state": self.live_state.copy() # Lưu trạng thái (Path tương đối -> Hash)
        }
        history.append(snapshot)

        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)

    # --- GIAO DIỆN & LOGIC KHÔI PHỤC (RESTORE) ---
    def open_restore_window(self):
        if self.observer is not None:
            messagebox.showwarning("Cảnh báo", "Vui lòng DỪNG giám sát trước khi Khôi phục!")
            return
        if not self.config.get("target_dir"):
            return
        if not self.authenticate("KHÔI PHỤC DỮ LIỆU"):
            return

        history_file = self.get_history_file()
        if not os.path.exists(history_file):
            messagebox.showinfo("Thông báo", "Thư mục này chưa có dữ liệu lịch sử nào.")
            return

        with open(history_file, "r", encoding="utf-8") as f:
            self.history_data = json.load(f)

        # Tạo cửa sổ phụ
        restore_win = tk.Toplevel(self.root)
        restore_win.title("Khôi phục Trạng thái Thư mục")
        restore_win.geometry("500x400")
        restore_win.grab_set() # Khóa cửa sổ chính lại

        ttk.Label(restore_win, text="Chọn một mốc thời gian để quay về:", font=("Arial", 10, "bold")).pack(pady=10)

        # Bảng danh sách các mốc thời gian
        listbox = tk.Listbox(restore_win, width=70, height=15)
        listbox.pack(padx=10, pady=5)
        for i, snap in enumerate(self.history_data):
            listbox.insert(tk.END, f"[{snap['timestamp']}] - {snap['description']}")

        def confirm_restore():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("Lỗi", "Vui lòng chọn một mốc thời gian!")
                return
            
            idx = selection[0]
            target_snapshot = self.history_data[idx]
            
            confirm = messagebox.askyesno("CẢNH BÁO NGUY HIỂM", 
                "Việc khôi phục sẽ XÓA SẠCH các file hiện tại trong thư mục và đưa về trạng thái trong quá khứ.\nBạn có chắc chắn không?")
            
            if confirm:
                self.execute_restore(target_snapshot)
                restore_win.destroy()

        ttk.Button(restore_win, text="⚡ TIẾN HÀNH KHÔI PHỤC", command=confirm_restore).pack(pady=10)

    def execute_restore(self, snapshot):
        target_dir = self.config["target_dir"]
        self.write_log(f"Đang kiểm tra tính toàn vẹn của bản sao lưu...", "info")

        # BƯỚC 1: XÁC MINH (PRE-FLIGHT CHECK)
        # Kiểm tra xem toàn bộ file backup có tồn tại trong kho không trước khi xóa bất cứ thứ gì
        missing_files = []
        for rel_path, file_hash in snapshot["state"].items():
            src_backup = os.path.join(BACKUP_DIR, file_hash)
            if not os.path.exists(src_backup):
                missing_files.append(rel_path)

        if missing_files:
            error_msg = f"HỦY KHÔI PHỤC: Thiếu {len(missing_files)} file backup trong kho!\nVí dụ: {missing_files[0]}"
            self.write_log(error_msg, "warning_del")
            messagebox.showerror("Lỗi Khôi phục", error_msg + "\n\nHệ thống đã dừng lại để bảo vệ dữ liệu hiện tại của bạn.")
            return # DỪNG NGAY LẬP TỨC. KHÔNG XÓA GÌ CẢ.

        # BƯỚC 2: XÓA THƯ MỤC HIỆN TẠI (Đã an toàn 100%)
        self.write_log(f"Xác minh 100% an toàn. Bắt đầu khôi phục...", "warning_mod")
        try:
            for item in os.listdir(target_dir):
                item_path = os.path.join(target_dir, item)
                
                # TUYỆT ĐỐI BỎ QUA không xóa thư mục snapshots và file config của phần mềm
                if os.path.abspath(item_path) == os.path.abspath(SNAPSHOT_DIR) or item == CONFIG_FILE:
                    continue
                    
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)

            # BƯỚC 3: LẮP RÁP LẠI FILE
            restored_count = 0
            for rel_path, file_hash in snapshot["state"].items():
                src_backup = os.path.join(BACKUP_DIR, file_hash)
                dst_path = os.path.join(target_dir, rel_path)

                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_backup, dst_path)
                restored_count += 1

            messagebox.showinfo("Thành công", f"Khôi phục hoàn tất!\nĐã phục hồi {restored_count} files.")
            self.write_log("Khôi phục trạng thái thành công.", "info")

        except Exception as e:
            messagebox.showerror("Lỗi Nghiêm trọng", f"Lỗi trong quá trình khôi phục:\n{e}")

    # --- CORE EVENT LOGIC ---
    def write_log(self, message, tag=None):
        self.log_area.config(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def send_windows_notification(self, title, message):
        try: notification.notify(title=title, message=message, app_name="FIM Security", timeout=5)
        except Exception: pass

    def process_event(self, event_type, file_path):
        # BỎ QUA nếu hệ thống đang báo cáo sự kiện của chính thư mục Backup hoặc file Config
        if os.path.abspath(file_path).startswith(os.path.abspath(SNAPSHOT_DIR)):
            return
        if os.path.abspath(file_path) == os.path.abspath(CONFIG_FILE):
            return

        target_dir = self.config["target_dir"]
        rel_path = os.path.relpath(file_path, target_dir)

        def update_ui(msg, tag, noti_title):
            self.write_log(msg, tag)
            self.send_windows_notification(noti_title, msg)

        if event_type in ['created', 'modified']:
            new_hash = self.calculate_sha256(file_path)
            if not new_hash: return

            old_hash = self.live_state.get(rel_path)

            if event_type == 'created' and not old_hash:
                self.backup_file(file_path, new_hash)
                self.live_state[rel_path] = new_hash
                self.record_snapshot(f"Thêm mới file: {os.path.basename(file_path)}")
                self.root.after(0, update_ui, f"Tạo mới & Backup: {os.path.basename(file_path)}", "warning_add", "CẢNH BÁO FILE MỚI")
                
            elif old_hash and old_hash != new_hash:
                self.backup_file(file_path, new_hash)
                self.live_state[rel_path] = new_hash
                self.record_snapshot(f"Sửa đổi file: {os.path.basename(file_path)}")
                self.root.after(0, update_ui, f"Sửa đổi & Backup: {os.path.basename(file_path)}", "warning_mod", "CẢNH BÁO SỬA ĐỔI")
                
        elif event_type == 'deleted':
            if rel_path in self.live_state:
                del self.live_state[rel_path]
                self.record_snapshot(f"Xóa file: {os.path.basename(file_path)}")
                self.root.after(0, update_ui, f"Đã xóa: {os.path.basename(file_path)}", "warning_del", "CẢNH BÁO XÓA FILE")

    def toggle_monitor(self, is_auto=False):
        target_dir = self.dir_var.get().strip()
        if not target_dir or not os.path.exists(target_dir):
            if not is_auto: messagebox.showerror("Lỗi", "Chưa có cấu hình thư mục hợp lệ!")
            return

        if not is_auto:
            action = "DỪNG giám sát" if self.observer else "BẬT giám sát"
            if not self.authenticate(action): return 

        if self.observer is None:
            # 1. Gọi hàm đồng bộ ngoại tuyến an toàn
            self.live_state.clear()
            self.sync_offline_state()

            # 2. Bật API Watchdog thời gian thực
            event_handler = FIMEventHandler(self)
            self.observer = Observer()
            self.observer.schedule(event_handler, target_dir, recursive=True)
            self.observer.start()

            self.btn_monitor.config(text="⏹ DỪNG GIÁM SÁT")
            self.btn_restore.config(state="disabled")
            self.write_log(f"Đang giám sát & sao lưu tự động tại: {target_dir}", "info")
        else:
            # Tắt giám sát
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.btn_monitor.config(text="▶ BẮT ĐẦU GIÁM SÁT")
            self.btn_restore.config(state="normal") 
            self.write_log("Đã dừng giám sát an toàn.", "info")
            
    def sync_offline_state(self):
        """Hàm đối soát trạng thái thực tế của Windows so với lịch sử gần nhất"""
        target_dir = self.config.get("target_dir", "")
        if not target_dir or not os.path.exists(target_dir):
            return 0

        last_known_state = {}
        history_file = self.get_history_file()
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                try:
                    history = json.load(f)
                    if history:
                        last_known_state = history[-1]["state"]
                except: pass

        current_os_files = {}
        snapshot_abs = os.path.abspath(SNAPSHOT_DIR)
        
        # Quét hệ điều hành
        for root, _, files in os.walk(target_dir):
            if os.path.abspath(root).startswith(snapshot_abs): continue
            for file in files:
                if file == CONFIG_FILE: continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, target_dir)
                current_os_files[rel_path] = full_path

        offline_changes_count = 0
        
        if last_known_state:
            # 1. Kiểm tra Xóa và Sửa
            for rel_path, old_hash in last_known_state.items():
                if rel_path not in current_os_files:
                    self.write_log(f"[OFFLINE] File bị xóa lén lút: {rel_path}", "warning_del")
                    offline_changes_count += 1
                else:
                    full_path = current_os_files[rel_path]
                    new_hash = self.calculate_sha256(full_path)
                    
                    # FIX LỖI CRASH NGẦM: Bỏ qua nếu file đang bị OS khóa
                    if new_hash is None:
                        self.live_state[rel_path] = old_hash
                        continue
                        
                    if new_hash != old_hash:
                        self.backup_file(full_path, new_hash)
                        self.live_state[rel_path] = new_hash
                        self.write_log(f"[OFFLINE] File bị sửa lén lút: {rel_path}", "warning_mod")
                        offline_changes_count += 1
                    else:
                        self.live_state[rel_path] = old_hash

            # 2. Kiểm tra Thêm mới
            for rel_path, full_path in current_os_files.items():
                if rel_path not in last_known_state:
                    new_hash = self.calculate_sha256(full_path)
                    if new_hash is not None:
                        self.backup_file(full_path, new_hash)
                        self.live_state[rel_path] = new_hash
                        self.write_log(f"[OFFLINE] File thêm lén lút: {rel_path}", "warning_add")
                        offline_changes_count += 1
        else:
            # Lần đầu tiên chạy
            for rel_path, full_path in current_os_files.items():
                new_hash = self.calculate_sha256(full_path)
                if new_hash is not None:
                    self.backup_file(full_path, new_hash)
                    self.live_state[rel_path] = new_hash

        # Cập nhật lịch sử
        if offline_changes_count > 0:
            self.record_snapshot(f"ĐỒNG BỘ NGOẠI TUYẾN: Phát hiện {offline_changes_count} thay đổi")
            self.send_windows_notification("Cảnh báo Ngoại tuyến", f"Phát hiện {offline_changes_count} thay đổi lén lút!")
        elif not last_known_state:
            self.record_snapshot("BẮT ĐẦU PHIÊN GIÁM SÁT ĐẦU TIÊN (Mốc gốc)")

        return offline_changes_count

    def run_startup_check(self):
        """Hàm tự động kích hoạt đối soát ngay khi mở App"""
        target_dir = self.config.get("target_dir", "")
        if target_dir and os.path.exists(target_dir):
            self.write_log(f"Đang tự động rà soát dữ liệu ngoại tuyến...", "info")
            self.root.update() # Ép giao diện hiển thị ngay lập tức
            self.live_state.clear()
            self.sync_offline_state()
            self.write_log("Hệ thống Sẵn sàng.", "info")
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--startup", action="store_true", help="Chạy ngầm")
    args = parser.parse_args()

    root = tk.Tk()
    app = FIMApplication(root, is_startup=args.startup)
    root.mainloop()