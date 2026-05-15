"""
MTC Casilla Bot — Panel de Control
Lanzador gráfico para Windows. Doble-click para abrir.
Sin consola (.pyw). Requiere Python 3.11+ y uv instalado.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import webbrowser
import os
import sys
import queue
from pathlib import Path
from datetime import datetime

# ── Rutas ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR     = PROJECT_ROOT / 'logs'

def find_uv() -> str:
    """Busca el ejecutable uv en rutas comunes de Windows."""
    candidates = [
        Path(os.environ.get('USERPROFILE', '')) / '.local' / 'bin' / 'uv.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'uv' / 'bin' / 'uv.exe',
        Path('C:/Users') / os.environ.get('USERNAME', '') / '.local' / 'bin' / 'uv.exe',
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return 'uv'  # Fallback: esperar que esté en PATH

UV = find_uv()

# ── Colores ─────────────────────────────────────────────────────────
BG       = '#0f172a'
SURFACE  = '#1e293b'
SURFACE2 = '#334155'
BORDER   = '#475569'
TEXT     = '#f1f5f9'
MUTED    = '#94a3b8'
PRIMARY  = '#3b82f6'
OK       = '#22c55e'
WARN     = '#f59e0b'
ERROR    = '#ef4444'
PURPLE   = '#7c3aed'


class BotLauncher:
    def __init__(self, root: tk.Tk):
        self.root    = root
        self.process = None
        self.running = False
        self.log_q   = queue.Queue()

        self._setup_window()
        self._build_ui()
        self._poll_log_queue()
        self._update_last_run()

    # ── Window ────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title('MTC Casilla Bot — Panel de Control')
        self.root.geometry('860x640')
        self.root.minsize(700, 500)
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

    # ── UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=SURFACE, pady=10)
        hdr.pack(fill='x')
        tk.Label(hdr, text='📬 MTC Casilla Bot', font=('Segoe UI', 14, 'bold'),
                 bg=SURFACE, fg=TEXT).pack(side='left', padx=16)
        tk.Label(hdr, text='Panel de Control', font=('Segoe UI', 10),
                 bg=SURFACE, fg=MUTED).pack(side='left')

        # Status bar
        status_frame = tk.Frame(self.root, bg=SURFACE2, pady=6)
        status_frame.pack(fill='x')

        self.lbl_status = tk.Label(status_frame, text='● Inactivo',
                                   font=('Segoe UI', 9, 'bold'), bg=SURFACE2, fg=MUTED)
        self.lbl_status.pack(side='left', padx=16)

        self.lbl_last = tk.Label(status_frame, text='Última ejecución: —',
                                 font=('Segoe UI', 9), bg=SURFACE2, fg=MUTED)
        self.lbl_last.pack(side='left', padx=8)

        # ── Opciones ──
        opt = tk.LabelFrame(self.root, text='  Opciones  ', font=('Segoe UI', 9),
                            bg=BG, fg=MUTED, bd=1, relief='flat', padx=12, pady=8)
        opt.pack(fill='x', padx=16, pady=(12, 0))

        tk.Label(opt, text='Desde:', bg=BG, fg=TEXT, font=('Segoe UI', 9)).grid(row=0, col=0, sticky='w')
        self.var_since = tk.StringVar(value='today')
        since_cb = ttk.Combobox(opt, textvariable=self.var_since, width=10,
                                values=['today', 'yesterday', 'all'], state='readonly')
        since_cb.grid(row=0, column=1, padx=(4, 20), sticky='w')

        self.var_dryrun = tk.BooleanVar(value=False)
        tk.Checkbutton(opt, text='Dry-run (solo vista previa, sin guardar)',
                       variable=self.var_dryrun, bg=BG, fg=TEXT,
                       selectcolor=SURFACE2, activebackground=BG,
                       font=('Segoe UI', 9)).grid(row=0, column=2, sticky='w')

        self.var_headed = tk.BooleanVar(value=False)
        tk.Checkbutton(opt, text='Headed (ver el navegador)',
                       variable=self.var_headed, bg=BG, fg=TEXT,
                       selectcolor=SURFACE2, activebackground=BG,
                       font=('Segoe UI', 9)).grid(row=0, column=3, padx=(20, 0), sticky='w')

        # ── Botones principales ──
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill='x', padx=16, pady=10)

        self.btn_run = tk.Button(
            btn_frame, text='▶  Ejecutar ahora', font=('Segoe UI', 11, 'bold'),
            bg=PRIMARY, fg='white', relief='flat', padx=20, pady=8,
            cursor='hand2', command=self.run_bot, activebackground='#2563eb',
            activeforeground='white',
        )
        self.btn_run.pack(side='left')

        self.btn_stop = tk.Button(
            btn_frame, text='■  Detener', font=('Segoe UI', 10),
            bg=ERROR, fg='white', relief='flat', padx=14, pady=8,
            cursor='hand2', command=self.stop_bot, state='disabled',
            activebackground='#dc2626', activeforeground='white',
        )
        self.btn_stop.pack(side='left', padx=(8, 0))

        tk.Button(
            btn_frame, text='📊  Dashboard', font=('Segoe UI', 10),
            bg=SURFACE2, fg=TEXT, relief='flat', padx=14, pady=8,
            cursor='hand2', command=self.open_dashboard,
            activebackground=BORDER, activeforeground=TEXT,
        ).pack(side='left', padx=(8, 0))

        tk.Button(
            btn_frame, text='📁  Logs', font=('Segoe UI', 10),
            bg=SURFACE2, fg=TEXT, relief='flat', padx=14, pady=8,
            cursor='hand2', command=self.open_logs_dir,
            activebackground=BORDER, activeforeground=TEXT,
        ).pack(side='left', padx=(8, 0))

        tk.Button(
            btn_frame, text='🔍  Doctor', font=('Segoe UI', 10),
            bg=SURFACE2, fg=TEXT, relief='flat', padx=14, pady=8,
            cursor='hand2', command=self.run_doctor,
            activebackground=BORDER, activeforeground=TEXT,
        ).pack(side='left', padx=(8, 0))

        # ── Progreso ──
        prog_frame = tk.Frame(self.root, bg=BG)
        prog_frame.pack(fill='x', padx=16, pady=(0, 4))

        self.progress = ttk.Progressbar(prog_frame, mode='indeterminate', length=400)
        self.progress.pack(side='left', fill='x', expand=True)

        self.lbl_ruc = tk.Label(prog_frame, text='', font=('Segoe UI', 8),
                                bg=BG, fg=MUTED)
        self.lbl_ruc.pack(side='left', padx=(8, 0))

        # ── Log output ──
        log_frame = tk.LabelFrame(self.root, text='  Registro de ejecución  ',
                                  font=('Segoe UI', 9), bg=BG, fg=MUTED,
                                  bd=1, relief='flat', padx=4, pady=4)
        log_frame.pack(fill='both', expand=True, padx=16, pady=(4, 8))

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=('Consolas', 9),
            bg='#020817', fg=TEXT,
            insertbackground=TEXT,
            relief='flat',
            state='disabled',
            wrap='word',
        )
        self.log_text.pack(fill='both', expand=True)

        # Tags para colores en el log
        self.log_text.tag_config('INFO',  foreground=TEXT)
        self.log_text.tag_config('OK',    foreground=OK)
        self.log_text.tag_config('WARN',  foreground=WARN)
        self.log_text.tag_config('ERROR', foreground=ERROR)
        self.log_text.tag_config('DIM',   foreground=MUTED)
        self.log_text.tag_config('RUC',   foreground='#93c5fd')

        # Footer
        footer = tk.Frame(self.root, bg=SURFACE, pady=4)
        footer.pack(fill='x', side='bottom')
        tk.Label(footer, text=f'Proyecto: {PROJECT_ROOT}',
                 font=('Segoe UI', 8), bg=SURFACE, fg=MUTED).pack(side='left', padx=12)
        tk.Button(footer, text='Limpiar log', font=('Segoe UI', 8),
                  bg=SURFACE, fg=MUTED, relief='flat', bd=0,
                  cursor='hand2', command=self.clear_log).pack(side='right', padx=12)

    # ── Acciones ─────────────────────────────────────────────────
    def run_bot(self):
        if self.running:
            return

        cmd = [UV, 'run', '--project', str(PROJECT_ROOT), 'mtc-bot', 'run',
               '--since', self.var_since.get()]
        if self.var_dryrun.get():
            cmd.append('--dry-run')
        if self.var_headed.get():
            cmd.append('--headed')

        self._set_running(True)
        self.log_append(f'\n{"─"*60}\n', 'DIM')
        self.log_append(f'[{now()}] Iniciando: {" ".join(cmd[2:])}\n', 'DIM')

        def worker():
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    cwd=str(PROJECT_ROOT),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                )
                for line in iter(self.process.stdout.readline, ''):
                    self.log_q.put(line)
                self.process.wait()
                rc = self.process.returncode
                self.log_q.put(f'[{now()}] Proceso terminado (código {rc})\n')
                self.log_q.put('__DONE__')
            except Exception as exc:
                self.log_q.put(f'[ERROR] {exc}\n')
                self.log_q.put('__DONE__')

        threading.Thread(target=worker, daemon=True).start()

    def stop_bot(self):
        if self.process and self.running:
            try:
                self.process.terminate()
                self.log_append(f'[{now()}] Ejecución cancelada por el usuario.\n', 'WARN')
            except Exception:
                pass

    def run_doctor(self):
        cmd = [UV, 'run', '--project', str(PROJECT_ROOT), 'mtc-bot', 'doctor']
        self._set_running(True)
        self.log_append(f'\n[{now()}] Ejecutando doctor...\n', 'DIM')

        def worker():
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding='utf-8', errors='replace', cwd=str(PROJECT_ROOT),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                )
                out = (result.stdout or '') + (result.stderr or '')
                for line in out.splitlines(keepends=True):
                    self.log_q.put(line)
                self.log_q.put('__DONE__')
            except Exception as exc:
                self.log_q.put(f'[ERROR] {exc}\n')
                self.log_q.put('__DONE__')

        threading.Thread(target=worker, daemon=True).start()

    def open_dashboard(self):
        webbrowser.open('https://canazachyub.github.io/mtc-casilla-bot/')

    def open_logs_dir(self):
        LOGS_DIR.mkdir(exist_ok=True)
        os.startfile(str(LOGS_DIR))

    def clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    # ── Helpers ──────────────────────────────────────────────────
    def _set_running(self, on: bool):
        self.running = on
        if on:
            self.btn_run.configure(state='disabled', bg=BORDER)
            self.btn_stop.configure(state='normal')
            self.lbl_status.configure(text='● Ejecutando...', fg=WARN)
            self.progress.start(12)
        else:
            self.btn_run.configure(state='normal', bg=PRIMARY)
            self.btn_stop.configure(state='disabled')
            self.lbl_status.configure(text='● Inactivo', fg=MUTED)
            self.progress.stop()
            self._update_last_run()

    def _update_last_run(self):
        LOGS_DIR.mkdir(exist_ok=True)
        logs = sorted(LOGS_DIR.glob('run-*.log'), reverse=True)
        if logs:
            ts = logs[0].stem.replace('run-', '')
            self.lbl_last.configure(text=f'Última ejecución: {ts}')

    def log_append(self, text: str, tag: str = 'INFO'):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', text, tag)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _classify_line(self, line: str) -> str:
        l = line.lower()
        if any(x in l for x in ['error', 'failed', 'exception', '✗', 'traceback']):
            return 'ERROR'
        if any(x in l for x in ['warning', 'warn', '⚠']):
            return 'WARN'
        if any(x in l for x in ['✓', '✅', 'ok', 'success', 'completado', 'subido', 'procesada']):
            return 'OK'
        if any(x in l for x in ['ruc', 'citv', '206', '205', '209', 'scraping', 'login']):
            return 'RUC'
        return 'INFO'

    def _poll_log_queue(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                if line == '__DONE__':
                    self._set_running(False)
                    break
                tag = self._classify_line(line)
                # Extraer y mostrar RUC en curso
                if 'ruc' in line.lower() and any(c.isdigit() for c in line):
                    import re
                    m = re.search(r'\d{11}', line)
                    if m:
                        self.lbl_ruc.configure(text=f'RUC: {m.group()}')
                self.log_append(line, tag)
        except Exception:
            pass
        self.root.after(100, self._poll_log_queue)


def now() -> str:
    return datetime.now().strftime('%H:%M:%S')


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TProgressbar', troughcolor=SURFACE2, background=PRIMARY, thickness=6)
    style.configure('TCombobox', fieldbackground=SURFACE2, background=SURFACE2,
                    foreground=TEXT, selectbackground=SURFACE2)

    app = BotLauncher(root)
    root.protocol('WM_DELETE_WINDOW', root.destroy)
    root.mainloop()


if __name__ == '__main__':
    main()
