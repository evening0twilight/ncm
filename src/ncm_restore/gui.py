"""Local drag-and-drop desktop interface for NCM conversion."""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from typing import Callable, Iterable

from .transcode import FORMATS
from .workflow import collect_sources, run_batch

BG = "#F4F6F9"
CARD = "#FFFFFF"
TEXT = "#172033"
MUTED = "#667085"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
BORDER = "#D0D5DD"
DROP_BG = "#EFF6FF"
DROP_ACTIVE = "#DBEAFE"
SUCCESS = "#15803D"
DANGER = "#B42318"


def target_from_label(label: str) -> str:
    for key, value in FORMATS.items():
        if value["label"] == label:
            return key
    raise ValueError(f"未知目标格式：{label}")


def merge_input_paths(existing: Iterable[Path], candidates: Iterable[Path]) -> tuple[list[Path], list[str]]:
    """Return unique valid NCM files/folders plus human-readable rejection messages."""
    merged = list(existing)
    identities = {path.resolve(strict=False) for path in merged}
    rejected: list[str] = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.exists():
            rejected.append(f"路径不存在：{path}")
            continue
        if path.is_file() and path.suffix.lower() != ".ncm":
            rejected.append(f"不是 NCM 文件：{path.name}")
            continue
        if not path.is_file() and not path.is_dir():
            rejected.append(f"不支持的路径：{path}")
            continue
        identity = path.resolve(strict=False)
        if identity not in identities:
            merged.append(path)
            identities.add(identity)
    return merged, rejected


def format_hint(target: str) -> str:
    hints = {
        "original": "推荐 · 直接恢复内部 FLAC/MP3，不重新编码",
        "wav": "无损 · 文件较大，保留采样率、声道与位深",
        "flac": "无损 · 体积较小，适合支持 FLAC 的播放器",
        "alac": "无损 · M4A 容器，适合 Apple 设备",
        "mp3": "有损 · 320 kb/s，兼容性最好",
        "aac": "有损 · 256 kb/s，M4A 容器",
        "opus": "有损 · 192 kb/s VBR，体积较小",
    }
    return hints[target]


def _center_window(root: object, width: int, height: int) -> None:
    root.update_idletasks()
    x = max((root.winfo_screenwidth() - width) // 2, 0)
    y = max((root.winfo_screenheight() - height) // 2, 0)
    root.geometry(f"{width}x{height}+{x}+{y}")


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from tkinter import font as tkfont
    except ImportError as exc:
        raise SystemExit("桌面界面需要 Tk。macOS Homebrew Python 请安装匹配版本的 python-tk") from exc
    try:
        from tkinterdnd2 import COPY, DND_FILES, TkinterDnD
    except ImportError as exc:
        raise SystemExit("拖拽界面依赖 tkinterdnd2，请重新运行：python -m pip install -e .") from exc

    root = TkinterDnD.Tk()
    root.title("NCM 本地音频转换")
    root.configure(bg=BG)
    root.minsize(820, 620)
    _center_window(root, 980, 720)

    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(size=11)
    root.option_add("*Font", default_font)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("App.TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED)
    style.configure("Treeview", rowheight=28, background=CARD, fieldbackground=CARD, borderwidth=0)
    style.configure("Treeview.Heading", padding=(8, 7), font=(default_font.actual("family"), 11, "bold"))
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#FFFFFF")])
    style.configure("TButton", padding=(12, 7))
    style.configure("Horizontal.TProgressbar", troughcolor="#E5E7EB", background=ACCENT, borderwidth=0)

    messages: queue.Queue[tuple] = queue.Queue()
    inputs: list[Path] = []
    busy = False
    interactive_widgets: list[object] = []

    shell = ttk.Frame(root, style="App.TFrame", padding=(24, 20, 24, 18))
    shell.grid(row=0, column=0, sticky="nsew")
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)
    shell.columnconfigure(0, weight=1)
    shell.rowconfigure(3, weight=2, minsize=82)
    shell.rowconfigure(7, weight=1, minsize=74)

    header = ttk.Frame(shell, style="App.TFrame")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
    header.columnconfigure(0, weight=1)
    ttk.Label(
        header,
        text="NCM 本地音频转换",
        font=(default_font.actual("family"), 24, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        header,
        text="拖入文件即可开始 · 默认原样恢复 · 源文件始终保留",
        style="Muted.TLabel",
    ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    drop_card = tk.Frame(
        shell,
        bg=DROP_BG,
        highlightbackground="#93C5FD",
        highlightcolor=ACCENT,
        highlightthickness=2,
        cursor="hand2",
        height=102,
    )
    drop_card.grid(row=1, column=0, sticky="ew")
    drop_card.grid_propagate(False)
    drop_card.columnconfigure(0, weight=1)
    drop_card.rowconfigure(0, weight=1)
    drop_content = tk.Frame(drop_card, bg=DROP_BG, cursor="hand2")
    drop_content.grid(row=0, column=0)
    drop_title = tk.Label(
        drop_content,
        text="⇩  把 NCM 文件或文件夹拖到这里",
        bg=DROP_BG,
        fg=ACCENT,
        font=(default_font.actual("family"), 16, "bold"),
        cursor="hand2",
    )
    drop_title.pack()
    drop_subtitle = tk.Label(
        drop_content,
        text="也可以点击此区域选择多个 .ncm 文件",
        bg=DROP_BG,
        fg=MUTED,
        cursor="hand2",
    )
    drop_subtitle.pack(pady=(6, 0))

    queue_bar = ttk.Frame(shell, style="App.TFrame")
    queue_bar.grid(row=2, column=0, sticky="ew", pady=(12, 7))
    queue_bar.columnconfigure(0, weight=1)
    queue_label = ttk.Label(queue_bar, text="待转换  0 项", font=(default_font.actual("family"), 12, "bold"))
    queue_label.grid(row=0, column=0, sticky="w")

    queue_actions = ttk.Frame(queue_bar, style="App.TFrame")
    queue_actions.grid(row=0, column=1, sticky="e")

    input_frame = ttk.Frame(shell, style="Card.TFrame")
    input_frame.grid(row=3, column=0, sticky="nsew")
    input_frame.rowconfigure(0, weight=1)
    input_frame.columnconfigure(0, weight=1)
    input_tree = ttk.Treeview(
        input_frame,
        columns=("name", "kind", "path"),
        show="headings",
        height=5,
        selectmode="extended",
    )
    input_tree.heading("name", text="名称")
    input_tree.heading("kind", text="类型")
    input_tree.heading("path", text="位置")
    input_tree.column("name", width=260, minwidth=150)
    input_tree.column("kind", width=90, minwidth=80, stretch=False, anchor="center")
    input_tree.column("path", width=520, minwidth=240)
    input_scroll = ttk.Scrollbar(input_frame, orient="vertical", command=input_tree.yview)
    input_tree.configure(yscrollcommand=input_scroll.set)
    input_tree.grid(row=0, column=0, sticky="nsew")
    input_scroll.grid(row=0, column=1, sticky="ns")

    options = ttk.Frame(shell, style="Card.TFrame", padding=(14, 12))
    options.grid(row=4, column=0, sticky="ew", pady=(14, 0))
    options.columnconfigure(1, weight=3)
    options.columnconfigure(2, weight=2)

    ttk.Label(options, text="输出目录", style="Card.TLabel", font=(default_font.actual("family"), 11, "bold")).grid(row=0, column=0, sticky="w")
    output_var = tk.StringVar()
    output_entry = ttk.Entry(options, textvariable=output_var)
    output_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(12, 10))
    choose_output_button = ttk.Button(options, text="选择目录…")
    choose_output_button.grid(row=0, column=3, sticky="ew")
    ttk.Label(options, text="留空时输出到源文件旁的 recovered 文件夹", style="CardMuted.TLabel").grid(row=1, column=1, columnspan=3, sticky="w", pady=(4, 8))

    ttk.Label(options, text="目标格式", style="Card.TLabel", font=(default_font.actual("family"), 11, "bold")).grid(row=3, column=0, sticky="w")
    format_var = tk.StringVar(value=FORMATS["original"]["label"])
    format_box = ttk.Combobox(
        options,
        textvariable=format_var,
        values=[item["label"] for item in FORMATS.values()],
        state="readonly",
        width=34,
    )
    format_box.grid(row=3, column=1, sticky="ew", padx=(12, 14))
    hint_var = tk.StringVar(value=format_hint("original"))
    ttk.Label(options, textvariable=hint_var, style="CardMuted.TLabel", wraplength=360).grid(row=3, column=2, sticky="w")
    recursive = tk.BooleanVar(value=True)
    recursive_button = ttk.Checkbutton(options, text="文件夹包含子目录", variable=recursive)
    recursive_button.grid(row=3, column=3, sticky="e", padx=(10, 0))

    progress_area = ttk.Frame(shell, style="App.TFrame")
    progress_area.grid(row=5, column=0, sticky="ew", pady=(14, 8))
    progress_area.columnconfigure(0, weight=1)
    progress = ttk.Progressbar(progress_area, mode="determinate")
    progress.grid(row=0, column=0, sticky="ew")
    status_var = tk.StringVar(value="添加 NCM 文件后即可转换")
    status_label = ttk.Label(progress_area, textvariable=status_var, style="Muted.TLabel")
    status_label.grid(row=1, column=0, sticky="w", pady=(5, 0))

    result_heading = ttk.Label(shell, text="转换结果", font=(default_font.actual("family"), 12, "bold"))
    result_heading.grid(row=6, column=0, sticky="w", pady=(2, 7))
    result_frame = ttk.Frame(shell, style="Card.TFrame")
    result_frame.grid(row=7, column=0, sticky="nsew")
    result_frame.rowconfigure(0, weight=1)
    result_frame.columnconfigure(0, weight=1)
    result_tree = ttk.Treeview(
        result_frame,
        columns=("status", "source", "detail"),
        show="headings",
        height=4,
    )
    for column, title, width in (
        ("status", "状态", 74),
        ("source", "源文件", 280),
        ("detail", "输出位置或失败原因", 540),
    ):
        result_tree.heading(column, text=title)
        result_tree.column(column, width=width, stretch=column != "status")
    result_scroll = ttk.Scrollbar(result_frame, orient="vertical", command=result_tree.yview)
    result_tree.configure(yscrollcommand=result_scroll.set)
    result_tree.grid(row=0, column=0, sticky="nsew")
    result_scroll.grid(row=0, column=1, sticky="ns")

    action_bar = ttk.Frame(shell, style="App.TFrame")
    action_bar.grid(row=8, column=0, sticky="ew", pady=(14, 0))
    action_bar.columnconfigure(0, weight=1)
    safety_label = ttk.Label(action_bar, text="✓ 不覆盖已有文件  ·  ✓ 不删除源文件", foreground=SUCCESS)
    safety_label.grid(row=0, column=0, sticky="w")
    start_button = tk.Button(
        action_bar,
        text="开始转换",
        command=lambda: start(),
        bg=ACCENT,
        activebackground=ACCENT_HOVER,
        fg="#FFFFFF",
        activeforeground="#FFFFFF",
        disabledforeground="#D1D5DB",
        font=(default_font.actual("family"), 14, "bold"),
        relief="flat",
        borderwidth=0,
        padx=28,
        pady=11,
        cursor="hand2",
        state="disabled",
    )
    start_button.grid(row=0, column=1, sticky="e")

    def set_drop_style(active: bool) -> None:
        color = DROP_ACTIVE if active else DROP_BG
        border = ACCENT if active else "#93C5FD"
        drop_card.configure(bg=color, highlightbackground=border)
        drop_content.configure(bg=color)
        drop_title.configure(bg=color)
        drop_subtitle.configure(bg=color)

    def update_start_button() -> None:
        if busy:
            start_button.configure(text="转换中…", state="disabled", bg="#94A3B8")
        elif inputs:
            start_button.configure(text=f"开始转换（{len(inputs)}）", state="normal", bg=ACCENT)
        else:
            start_button.configure(text="开始转换", state="disabled", bg="#94A3B8")

    def redraw_inputs() -> None:
        input_tree.delete(*input_tree.get_children())
        for index, path in enumerate(inputs):
            kind = "文件夹" if path.is_dir() else "NCM 文件"
            input_tree.insert("", "end", iid=str(index), values=(path.name, kind, str(path.parent)))
        queue_label.configure(text=f"待转换  {len(inputs)} 项")
        update_start_button()

    def add_paths(paths: Iterable[Path]) -> None:
        nonlocal inputs
        if busy:
            status_var.set("当前批次正在转换，请完成后再添加文件")
            return
        previous = len(inputs)
        inputs, rejected = merge_input_paths(inputs, paths)
        added = len(inputs) - previous
        redraw_inputs()
        if added:
            status_var.set(f"已加入 {added} 项，共 {len(inputs)} 项 · 现在可以点击右下角开始转换")
        elif rejected:
            status_var.set(rejected[0])
        else:
            status_var.set("这些项目已经在列表中")
        if rejected:
            messagebox.showwarning("部分项目未加入", "\n".join(rejected[:8]))

    def add_files() -> None:
        selected = filedialog.askopenfilenames(
            title="选择 NCM 文件",
            filetypes=[("NCM 音频", "*.ncm"), ("所有文件", "*")],
        )
        add_paths(Path(item) for item in selected)

    def add_folder() -> None:
        selected = filedialog.askdirectory(title="选择包含 NCM 的文件夹")
        if selected:
            add_paths([Path(selected)])

    def remove_selected() -> None:
        nonlocal inputs
        indexes = sorted((int(item) for item in input_tree.selection()), reverse=True)
        for index in indexes:
            inputs.pop(index)
        redraw_inputs()
        status_var.set(f"剩余 {len(inputs)} 项" if inputs else "添加 NCM 文件后即可转换")

    def clear_inputs() -> None:
        nonlocal inputs
        inputs = []
        redraw_inputs()
        status_var.set("列表已清空")

    def choose_output() -> None:
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            output_var.set(selected)

    add_file_button = ttk.Button(queue_actions, text="添加文件…", command=add_files)
    add_file_button.pack(side="left", padx=(0, 6))
    add_folder_button = ttk.Button(queue_actions, text="添加文件夹…", command=add_folder)
    add_folder_button.pack(side="left", padx=(0, 6))
    remove_button = ttk.Button(queue_actions, text="移除选中", command=remove_selected)
    remove_button.pack(side="left", padx=(0, 6))
    clear_button = ttk.Button(queue_actions, text="清空", command=clear_inputs)
    clear_button.pack(side="left")
    choose_output_button.configure(command=choose_output)
    interactive_widgets.extend([
        add_file_button,
        add_folder_button,
        remove_button,
        clear_button,
        choose_output_button,
        output_entry,
        format_box,
        recursive_button,
    ])

    def on_format_changed(*_: object) -> None:
        hint_var.set(format_hint(target_from_label(format_var.get())))

    format_var.trace_add("write", on_format_changed)

    def on_drop_enter(_: object) -> str:
        if not busy:
            set_drop_style(True)
            drop_title.configure(text="松开即可加入转换列表")
        return COPY

    def on_drop_leave(_: object) -> str:
        set_drop_style(False)
        drop_title.configure(text="⇩  把 NCM 文件或文件夹拖到这里")
        return COPY

    def on_drop(event: object) -> str:
        on_drop_leave(event)
        try:
            raw_paths = root.tk.splitlist(event.data)
            add_paths(Path(item) for item in raw_paths)
        except (tk.TclError, AttributeError, ValueError) as exc:
            messagebox.showerror("无法读取拖入内容", str(exc))
        return COPY

    for widget in (drop_card, drop_content, drop_title, drop_subtitle, input_tree):
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<DropEnter>>", on_drop_enter)
        widget.dnd_bind("<<DropLeave>>", on_drop_leave)
        widget.dnd_bind("<<Drop>>", on_drop)
    for widget in (drop_card, drop_content, drop_title, drop_subtitle):
        widget.bind("<Button-1>", lambda _: add_files())

    def set_controls_enabled(enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in interactive_widgets:
            if widget is format_box:
                widget.configure(state="readonly" if enabled else "disabled")
            else:
                widget.configure(state=state)
        update_start_button()

    def worker(sources: list[Path], output: Path | None, target: str, initial_failures: list[dict]) -> None:
        try:
            for failure in initial_failures:
                messages.put(("result", 0, len(sources), failure, False))

            def send(index: int, total: int, item: dict, ok: bool) -> None:
                messages.put(("result", index, total, item, ok))

            def send_start(index: int, total: int, source: Path) -> None:
                messages.put(("start", index, total, str(source)))

            successes, failures = run_batch(sources, output, target, send, send_start)
            messages.put(("done", len(successes), len(failures) + len(initial_failures)))
        except Exception as exc:
            messages.put(("fatal", str(exc)))

    def start() -> None:
        nonlocal busy
        if busy or not inputs:
            return
        sources, failures = collect_sources(inputs, recursive.get())
        if not sources:
            detail = failures[0]["error"] if failures else "未找到 NCM 文件"
            messagebox.showinfo("无法开始转换", detail)
            return
        result_tree.delete(*result_tree.get_children())
        progress.configure(maximum=max(len(sources), 1), value=0)
        status_var.set(f"准备处理 {len(sources)} 个文件…")
        busy = True
        set_controls_enabled(False)
        threading.Thread(
            target=worker,
            args=(
                sources,
                Path(output_var.get()) if output_var.get().strip() else None,
                target_from_label(format_var.get()),
                failures,
            ),
            daemon=True,
        ).start()

    def poll() -> None:
        nonlocal busy
        try:
            while True:
                event = messages.get_nowait()
                if event[0] == "start":
                    _, index, total, source = event
                    status_var.set(f"正在转换 {index}/{total} · {Path(source).name}")
                elif event[0] == "result":
                    _, index, total, item, ok = event
                    detail = item.get("output", "") if ok else item.get("error", "")
                    if ok and item.get("notes"):
                        detail += " · " + "；".join(item["notes"])
                    result_tree.insert("", "end", values=("成功" if ok else "失败", Path(item["source"]).name, detail))
                    progress.configure(value=index)
                    result_tree.yview_moveto(1)
                    status_var.set(f"已处理 {index}/{total} 个文件")
                elif event[0] == "done":
                    busy = False
                    set_controls_enabled(True)
                    status_var.set(f"转换完成 · 成功 {event[1]} · 失败 {event[2]}")
                elif event[0] == "fatal":
                    busy = False
                    set_controls_enabled(True)
                    status_var.set("转换失败")
                    messagebox.showerror("转换失败", event[1])
        except queue.Empty:
            pass
        root.after(100, poll)

    def close() -> None:
        if busy:
            messagebox.showinfo("正在转换", "请等待当前批次完成后再关闭窗口。")
        else:
            root.destroy()

    root.bind("<Return>", lambda _: start())
    if sys.platform == "darwin":
        root.bind("<Command-o>", lambda _: add_files())
    else:
        root.bind("<Control-o>", lambda _: add_files())
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    redraw_inputs()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
