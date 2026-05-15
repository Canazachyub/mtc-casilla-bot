"""
MTC Casilla Bot — Panel de Control
Lanzador grafico para Windows. Doble-click en Abrir-Panel-MTC.bat para abrir.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import webbrowser
import os
import sys
import queue
import re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR     = PROJECT_ROOT / 'logs'

# ── Paleta de colores ──────────────────────────────────────────────
BG      = '#0f172a'
SURFACE = '#1e293b'
SURF2   = '#334155'
BORDER  = '#475569'
TEXT    = '#f1f5f9'
MUTED   = '#94a3b8'
PRIMARY = '#3b82f6'
OK      = '#22c55e'
WARN    = '#f59e0b'
ERROR   = '#ef4444'


def find_uv() -> str:
    candidates = [
        Path(os.environ.get('USERPROFILE', '')) / '.local' / 'bin' / 'uv.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'uv' / 'bin' / 'uv.exe',
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return 'uv'


UV = find_uv()


def ts() -> str:
    return datetime.now().strftime('%H:%M:%S')


class App:
    def __init__(self, root: tk.Tk):
        self.root    = root
        self.process = None
        self.running = False
        self.q       = queue.Queue()
        self._build()
        self._poll()
        self._refresh_last_run()

    # ── Construccion de la UI ─────────────────────────────────────
    def _build(self):
        self.root.title('MTC Casilla Bot — Panel de Control')
        self.root.geometry('860x640')
        self.root.minsize(720, 500)
        self.root.configure(bg=BG)

        # Header
        hdr = tk.Frame(self.root, bg=SURFACE, pady=10)
        hdr.pack(fill='x')
        tk.Label(hdr, text='📬  MTC Casilla Bot',
                 font=('Segoe UI', 14, 'bold'), bg=SURFACE, fg=TEXT).pack(side='left', padx=16)
        tk.Label(hdr, text='Panel de Control',
                 font=('Segoe UI', 10), bg=SURFACE, fg=MUTED).pack(side='left')

        # Barra de estado
        sb = tk.Frame(self.root, bg=SURF2, pady=5)
        sb.pack(fill='x')
        self.lbl_status = tk.Label(sb, text='● Inactivo',
                                   font=('Segoe UI', 9, 'bold'), bg=SURF2, fg=MUTED)
        self.lbl_status.pack(side='left', padx=14)
        self.lbl_last = tk.Label(sb, text='Última ejecución: —',
                                 font=('Segoe UI', 9), bg=SURF2, fg=MUTED)
        self.lbl_last.pack(side='left', padx=6)

        # Opciones
        opt = tk.LabelFrame(self.root, text='  Opciones  ', font=('Segoe UI', 9),
                            bg=BG, fg=MUTED, bd=1, relief='flat', padx=12, pady=8)
        opt.pack(fill='x', padx=14, pady=(10, 0))

        tk.Label(opt, text='Desde:', bg=BG, fg=TEXT,
                 font=('Segoe UI', 9)).grid(row=0, column=0, sticky='w')

        self.var_since = tk.StringVar(value='today')
        ttk.Combobox(opt, textvariable=self.var_since, width=12,
                     values=['today', 'yesterday', 'all'],
                     state='readonly').grid(row=0, column=1, padx=(4, 20), sticky='w')

        self.var_dry = tk.BooleanVar(value=False)
        tk.Checkbutton(opt, text='Dry-run (solo vista previa)',
                       variable=self.var_dry, bg=BG, fg=TEXT,
                       selectcolor=SURF2, activebackground=BG,
                       font=('Segoe UI', 9)).grid(row=0, column=2, sticky='w')

        self.var_headed = tk.BooleanVar(value=False)
        tk.Checkbutton(opt, text='Headed (ver navegador + capturas)',
                       variable=self.var_headed, bg=BG, fg=TEXT,
                       selectcolor=SURF2, activebackground=BG,
                       font=('Segoe UI', 9)).grid(row=0, column=3, padx=(20, 0), sticky='w')

        # Botones
        bf = tk.Frame(self.root, bg=BG)
        bf.pack(fill='x', padx=14, pady=10)

        self.btn_run = self._btn(bf, '▶  Ejecutar ahora', PRIMARY, self.do_run, bold=True)
        self.btn_run.pack(side='left')

        self.btn_stop = self._btn(bf, '■  Detener', ERROR, self.do_stop)
        self.btn_stop.pack(side='left', padx=(6, 0))
        self.btn_stop.configure(state='disabled')

        self._btn(bf, '🔍  Doctor',    SURF2, self.do_doctor).pack(side='left', padx=(6, 0))
        self._btn(bf, '📊  Dashboard', SURF2, self.open_dashboard).pack(side='left', padx=(6, 0))
        self._btn(bf, '📁  Logs',      SURF2, self.open_logs).pack(side='left', padx=(6, 0))
        self._btn(bf, '📸  Capturas',  SURF2, self.open_shots).pack(side='left', padx=(6, 0))

        # Progreso
        pf = tk.Frame(self.root, bg=BG)
        pf.pack(fill='x', padx=14, pady=(0, 4))
        self.progress = ttk.Progressbar(pf, mode='indeterminate')
        self.progress.pack(side='left', fill='x', expand=True)
        self.lbl_ruc = tk.Label(pf, text='', font=('Segoe UI', 8), bg=BG, fg=MUTED)
        self.lbl_ruc.pack(side='left', padx=(8, 0))

        # Log
        lf = tk.LabelFrame(self.root, text='  Registro de ejecución  ',
                            font=('Segoe UI', 9), bg=BG, fg=MUTED, bd=1, relief='flat',
                            padx=4, pady=4)
        lf.pack(fill='both', expand=True, padx=14, pady=(2, 6))

        self.log = scrolledtext.ScrolledText(
            lf, font=('Consolas', 9), bg='#020817', fg=TEXT,
            insertbackground=TEXT, relief='flat', state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True)
        self.log.tag_config('OK',    foreground=OK)
        self.log.tag_config('WARN',  foreground=WARN)
        self.log.tag_config('ERROR', foreground=ERROR)
        self.log.tag_config('DIM',   foreground=MUTED)
        self.log.tag_config('RUC',   foreground='#93c5fd')

        # Footer
        ft = tk.Frame(self.root, bg=SURFACE, pady=4)
        ft.pack(fill='x', side='bottom')
        tk.Label(ft, text=str(PROJECT_ROOT), font=('Segoe UI', 8),
                 bg=SURFACE, fg=MUTED).pack(side='left', padx=12)
        tk.Button(ft, text='Limpiar', font=('Segoe UI', 8), bg=SURFACE, fg=MUTED,
                  relief='flat', bd=0, cursor='hand2',
                  command=self._clear_log).pack(side='right', padx=12)

    def _btn(self, parent, text, color, cmd, bold=False):
        font = ('Segoe UI', 10, 'bold') if bold else ('Segoe UI', 10)
        return tk.Button(parent, text=text, font=font, bg=color, fg='white',
                         relief='flat', padx=14, pady=7, cursor='hand2',
                         command=cmd, activebackground=color, activeforeground='white')

    # ── Acciones ─────────────────────────────────────────────────
    def do_run(self):
        if self.running:
            return
        cmd = [UV, 'run', '--project', str(PROJECT_ROOT), 'mtc-bot', 'run',
               '--since', self.var_since.get()]
        if self.var_dry.get():
            cmd.append('--dry-run')
        if self.var_headed.get():
            cmd.append('--headed')

        self._set_busy(True)
        self._log(f'\n{"─"*60}\n', 'DIM')
        self._log(f'[{ts()}] Ejecutando: {" ".join(cmd[3:])}\n', 'DIM')
        self._spawn(cmd)

    def do_stop(self):
        if self.process:
            try:
                self.process.terminate()
                self._log(f'[{ts()}] Detenido por el usuario.\n', 'WARN')
            except Exception:
                pass

    def do_doctor(self):
        cmd = [UV, 'run', '--project', str(PROJECT_ROOT), 'mtc-bot', 'doctor']
        self._set_busy(True)
        self._log(f'\n[{ts()}] Ejecutando doctor...\n', 'DIM')
        self._spawn(cmd)

    def open_dashboard(self):
        webbrowser.open('https://canazachyub.github.io/mtc-casilla-bot/')

    def open_logs(self):
        LOGS_DIR.mkdir(exist_ok=True)
        os.startfile(str(LOGS_DIR))

    def open_shots(self):
        shots = PROJECT_ROOT / 'playwright-screenshots'
        shots.mkdir(exist_ok=True)
        os.startfile(str(shots))

    # ── Subprocess ───────────────────────────────────────────────
    def _spawn(self, cmd):
        def worker():
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                self.process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace',
                    cwd=str(PROJECT_ROOT), creationflags=flags)
                for line in iter(self.process.stdout.readline, ''):
                    self.q.put(line)
                self.process.wait()
                self.q.put(f'[{ts()}] Proceso finalizado (código {self.process.returncode})\n')
            except Exception as exc:
                self.q.put(f'[{ts()}] ERROR: {exc}\n')
            finally:
                self.q.put('__DONE__')

        threading.Thread(target=worker, daemon=True).start()

    # ── Poll queue ────────────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                line = self.q.get_nowait()
                if line == '__DONE__':
                    self._set_busy(False)
                    break
                tag = self._tag(line)
                m = re.search(r'\b(\d{11})\b', line)
                if m:
                    self.lbl_ruc.configure(text=f'RUC en curso: {m.group(1)}')
                self._log(line, tag)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _tag(self, line: str) -> str:
        l = line.lower()
        if any(x in l for x in ['error', 'failed', 'exception', '✗', 'traceback']):
            return 'ERROR'
        if any(x in l for x in ['warning', 'warn', '⚠', 'timeout']):
            return 'WARN'
        if any(x in l for x in ['✓', '✅', 'ok', 'success', 'completado', 'subido', 'skip']):
            return 'OK'
        if any(x in l for x in ['ruc', 'citv', 'login', 'inbox', 'scraping']):
            return 'RUC'
        return None

    # ── UI helpers ────────────────────────────────────────────────
    def _set_busy(self, on: bool):
        self.running = on
        state_run  = 'disabled' if on else 'normal'
        state_stop = 'normal'   if on else 'disabled'
        bg_run     = BORDER if on else PRIMARY
        self.btn_run.configure(state=state_run, bg=bg_run)
        self.btn_stop.configure(state=state_stop)
        self.lbl_status.configure(
            text='● Ejecutando...' if on else '● Inactivo',
            fg=WARN if on else MUTED)
        if on:
            self.progress.start(10)
        else:
            self.progress.stop()
            self.lbl_ruc.configure(text='')
            self._refresh_last_run()

    def _log(self, text: str, tag=None):
        self.log.configure(state='normal')
        if tag:
            self.log.insert('end', text, tag)
        else:
            self.log.insert('end', text)
        self.log.see('end')
        self.log.configure(state='disabled')

    def _clear_log(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    def _refresh_last_run(self):
        LOGS_DIR.mkdir(exist_ok=True)
        logs = sorted(LOGS_DIR.glob('run-*.log'), reverse=True)
        label = logs[0].stem.replace('run-', '') if logs else '—'
        self.lbl_last.configure(text=f'Última ejecución: {label}')


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TProgressbar', troughcolor=SURF2, background=PRIMARY, thickness=5)
    style.configure('TCombobox', fieldbackground=SURF2, background=SURF2,
                    foreground=TEXT, selectbackground=SURF2)
    App(root)
    root.protocol('WM_DELETE_WINDOW', root.destroy)
    root.mainloop()


if __name__ == '__main__':
    main()
