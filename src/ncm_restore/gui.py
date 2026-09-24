"""Modern local drag-and-drop desktop interface for NCM conversion."""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from typing import Iterable

from .transcode import FORMATS
from .workflow import collect_sources, run_batch

BG = "#F4F5F9"
CARD = "#FFFFFF"
SURFACE = "#F8F9FC"
TEXT = "#161A2B"
MUTED = "#72778A"
SUBTLE = "#9AA0B4"
BORDER = "#E4E6EF"
ACCENT = "#635BDF"
ACCENT_HOVER = "#5148C8"
ACCENT_SOFT = "#F0EFFF"
DROP_ACTIVE = "#E7E5FF"
SUCCESS = "#12A66A"
SUCCESS_SOFT = "#EAF8F2"
DANGER = "#E5484D"
DANGER_SOFT = "#FFF0F0"


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
        "original": "直接恢复内部 FLAC/MP3，不重新编码",
        "wav": "无损输出，文件较大，保留采样率、声道与位深",
        "flac": "无损压缩，体积更小，适合多数播放器",
        "alac": "无损 M4A，适合 Apple 设备",
        "mp3": "320 kb/s 有损输出，设备兼容性最好",
        "aac": "256 kb/s 有损 M4A，兼顾体积与兼容性",
        "opus": "192 kb/s VBR 有损输出，体积较小",
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
        from tkinter import filedialog, messagebox
        import customtkinter as ctk
    except ImportError as exc:
        raise SystemExit("桌面界面依赖 Tk 和 CustomTkinter，请重新运行：python -m pip install -e .") from exc
    try:
        from tkinterdnd2 import COPY, DND_FILES, TkinterDnD
    except ImportError as exc:
        raise SystemExit("拖拽界面依赖 tkinterdnd2，请重新运行：python -m pip install -e .") from exc

    class DragDropWindow(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self) -> None:
            super().__init__()
            self.TkdndVersion = TkinterDnD._require(self)

    ctk.set_appearance_mode("light")
    root = DragDropWindow()
    root.title("NCM 本地音频转换")
    root.configure(fg_color=BG)
    root.minsize(920, 680)
    _center_window(root, 1040, 760)

    title_font = ctk.CTkFont(size=26, weight="bold")
    heading_font = ctk.CTkFont(size=16, weight="bold")
    body_bold = ctk.CTkFont(size=13, weight="bold")
    body_font = ctk.CTkFont(size=13)
    small_font = ctk.CTkFont(size=11)

    messages: queue.Queue[tuple] = queue.Queue()
    inputs: list[Path] = []
    busy = False
    interactive_widgets: list[object] = []

    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=1)

    header = ctk.CTkFrame(root, fg_color="transparent", corner_radius=0)
    header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 16))
    header.grid_columnconfigure(1, weight=1)

    logo = ctk.CTkFrame(header, width=48, height=48, corner_radius=15, fg_color=ACCENT)
    logo.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
    logo.grid_propagate(False)
    ctk.CTkLabel(logo, text="N", text_color="#FFFFFF", font=ctk.CTkFont(size=21, weight="bold")).place(
        relx=0.5, rely=0.5, anchor="center"
    )

    ctk.CTkLabel(header, text="NCM 音频转换", text_color=TEXT, font=title_font, anchor="w").grid(
        row=0, column=1, sticky="sw"
    )
    ctk.CTkLabel(
        header,
        text="拖入文件，选择格式，一次完成",
        text_color=MUTED,
        font=body_font,
        anchor="w",
    ).grid(row=1, column=1, sticky="nw", pady=(2, 0))

    privacy_badge = ctk.CTkFrame(header, fg_color=SUCCESS_SOFT, corner_radius=18)
    privacy_badge.grid(row=0, column=2, rowspan=2, sticky="e")
    ctk.CTkLabel(
        privacy_badge,
        text="●  仅在本机处理",
        text_color=SUCCESS,
        font=small_font,
    ).pack(padx=14, pady=8)

    workspace = ctk.CTkFrame(root, fg_color="transparent", corner_radius=0)
    workspace.grid(row=1, column=0, sticky="nsew", padx=28)
    workspace.grid_columnconfigure(0, weight=3, uniform="workspace")
    workspace.grid_columnconfigure(1, weight=2, uniform="workspace")
    workspace.grid_rowconfigure(0, weight=1)

    queue_card = ctk.CTkFrame(workspace, fg_color=CARD, corner_radius=20, border_width=1, border_color=BORDER)
    queue_card.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
    queue_card.grid_columnconfigure(0, weight=1)
    queue_card.grid_rowconfigure(3, weight=1)

    queue_header = ctk.CTkFrame(queue_card, fg_color="transparent")
    queue_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 12))
    queue_header.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(queue_header, text="待转换文件", text_color=TEXT, font=heading_font).grid(row=0, column=0, sticky="w")
    queue_count = ctk.CTkLabel(
        queue_header,
        text="0 项",
        width=48,
        height=26,
        fg_color=ACCENT_SOFT,
        text_color=ACCENT,
        corner_radius=13,
        font=small_font,
    )
    queue_count.grid(row=0, column=1, sticky="w", padx=(10, 0))
    clear_button = ctk.CTkButton(
        queue_header,
        text="清空",
        width=58,
        height=30,
        corner_radius=10,
        fg_color="transparent",
        hover_color=SURFACE,
        text_color=MUTED,
        font=small_font,
    )
    clear_button.grid(row=0, column=2, sticky="e")

    drop_card = ctk.CTkFrame(
        queue_card,
        height=124,
        fg_color=ACCENT_SOFT,
        corner_radius=16,
        border_width=2,
        border_color="#C8C5FF",
        cursor="hand2",
    )
    drop_card.grid(row=1, column=0, sticky="ew", padx=20)
    drop_card.grid_propagate(False)
    drop_card.grid_columnconfigure(0, weight=1)
    drop_card.grid_rowconfigure(0, weight=1)
    drop_content = ctk.CTkFrame(drop_card, fg_color="transparent", cursor="hand2")
    drop_content.grid(row=0, column=0)
    drop_icon = ctk.CTkLabel(
        drop_content,
        text="＋",
        width=34,
        height=34,
        corner_radius=17,
        fg_color=ACCENT,
        text_color="#FFFFFF",
        font=ctk.CTkFont(size=20, weight="bold"),
        cursor="hand2",
    )
    drop_icon.pack(pady=(0, 8))
    drop_title = ctk.CTkLabel(
        drop_content,
        text="拖放 NCM 文件或文件夹",
        text_color=ACCENT,
        font=body_bold,
        cursor="hand2",
    )
    drop_title.pack()
    drop_subtitle = ctk.CTkLabel(
        drop_content,
        text="也可以点击这里选择文件",
        text_color=MUTED,
        font=small_font,
        cursor="hand2",
    )
    drop_subtitle.pack(pady=(3, 0))

    queue_actions = ctk.CTkFrame(queue_card, fg_color="transparent")
    queue_actions.grid(row=2, column=0, sticky="ew", padx=20, pady=(12, 10))
    queue_actions.grid_columnconfigure((0, 1), weight=1)
    add_file_button = ctk.CTkButton(
        queue_actions,
        text="＋  添加文件",
        height=34,
        corner_radius=11,
        fg_color=SURFACE,
        hover_color="#EEF0F6",
        text_color=TEXT,
        border_width=1,
        border_color=BORDER,
        font=small_font,
    )
    add_file_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    add_folder_button = ctk.CTkButton(
        queue_actions,
        text="＋  添加文件夹",
        height=34,
        corner_radius=11,
        fg_color=SURFACE,
        hover_color="#EEF0F6",
        text_color=TEXT,
        border_width=1,
        border_color=BORDER,
        font=small_font,
    )
    add_folder_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    input_list = ctk.CTkScrollableFrame(
        queue_card,
        fg_color=SURFACE,
        corner_radius=14,
        scrollbar_button_color="#D8DAE5",
        scrollbar_button_hover_color="#BFC3D2",
    )
    input_list.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
    input_list.grid_columnconfigure(0, weight=1)

    settings_card = ctk.CTkFrame(workspace, fg_color=CARD, corner_radius=20, border_width=1, border_color=BORDER)
    settings_card.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
    settings_card.grid_columnconfigure(0, weight=1)
    settings_card.grid_rowconfigure(8, weight=1)

    ctk.CTkLabel(settings_card, text="转换设置", text_color=TEXT, font=heading_font, anchor="w").grid(
        row=0, column=0, sticky="ew", padx=20, pady=(18, 16)
    )
    ctk.CTkLabel(settings_card, text="目标格式", text_color=MUTED, font=small_font, anchor="w").grid(
        row=1, column=0, sticky="ew", padx=20
    )
    format_var = tk.StringVar(value=FORMATS["original"]["label"])
    format_selector = ctk.CTkFrame(
        settings_card,
        height=40,
        corner_radius=12,
        fg_color=SURFACE,
        border_width=1,
        border_color=BORDER,
    )
    format_selector.grid(row=2, column=0, sticky="ew", padx=20, pady=(6, 10))
    format_selector.grid_columnconfigure(0, weight=1)
    format_display = ctk.CTkButton(
        format_selector,
        textvariable=format_var,
        height=38,
        corner_radius=11,
        fg_color="transparent",
        hover_color="#EEF0F6",
        text_color=TEXT,
        font=body_font,
        anchor="w",
    )
    format_display.grid(row=0, column=0, sticky="ew")
    format_arrow = ctk.CTkButton(
        format_selector,
        text="⌄",
        width=42,
        height=38,
        corner_radius=11,
        fg_color="transparent",
        hover_color="#E7E8F0",
        text_color=TEXT,
        font=ctk.CTkFont(size=18, weight="bold"),
    )
    format_arrow.grid(row=0, column=1, sticky="e")

    hint_var = tk.StringVar(value=format_hint("original"))
    hint_card = ctk.CTkFrame(settings_card, fg_color=ACCENT_SOFT, corner_radius=12)
    hint_card.grid(row=3, column=0, sticky="ew", padx=20)
    hint_card.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(hint_card, text="✓", text_color=ACCENT, font=body_bold).grid(row=0, column=0, padx=(12, 8), pady=10)
    ctk.CTkLabel(
        hint_card,
        textvariable=hint_var,
        text_color=ACCENT,
        font=small_font,
        anchor="w",
        justify="left",
        wraplength=260,
    ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=10)

    ctk.CTkLabel(settings_card, text="输出目录", text_color=MUTED, font=small_font, anchor="w").grid(
        row=4, column=0, sticky="ew", padx=20, pady=(16, 0)
    )
    output_row = ctk.CTkFrame(settings_card, fg_color="transparent")
    output_row.grid(row=5, column=0, sticky="ew", padx=20, pady=(6, 4))
    output_row.grid_columnconfigure(0, weight=1)
    output_var = tk.StringVar()
    output_entry = ctk.CTkEntry(
        output_row,
        textvariable=output_var,
        height=40,
        corner_radius=12,
        fg_color=SURFACE,
        border_color=BORDER,
        text_color=TEXT,
        placeholder_text="自动保存到 recovered 文件夹",
        placeholder_text_color=SUBTLE,
        font=small_font,
    )
    output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    choose_output_button = ctk.CTkButton(
        output_row,
        text="选择",
        width=64,
        height=40,
        corner_radius=12,
        fg_color=SURFACE,
        hover_color="#EEF0F6",
        text_color=TEXT,
        border_width=1,
        border_color=BORDER,
        font=small_font,
    )
    choose_output_button.grid(row=0, column=1)

    recursive = tk.BooleanVar(value=True)
    recursive_switch = ctk.CTkSwitch(
        settings_card,
        text="搜索文件夹中的子目录",
        variable=recursive,
        progress_color=ACCENT,
        button_color="#FFFFFF",
        button_hover_color="#FFFFFF",
        text_color=TEXT,
        font=small_font,
    )
    recursive_switch.grid(row=6, column=0, sticky="w", padx=20, pady=(12, 0))

    safety_card = ctk.CTkFrame(settings_card, fg_color=SUCCESS_SOFT, corner_radius=12)
    safety_card.grid(row=7, column=0, sticky="ew", padx=20, pady=(16, 0))
    ctk.CTkLabel(
        safety_card,
        text="✓ 保留源文件    ✓ 不覆盖已有文件",
        text_color=SUCCESS,
        font=small_font,
    ).pack(padx=12, pady=9)

    start_button = ctk.CTkButton(
        settings_card,
        text="添加文件后即可开始",
        height=48,
        corner_radius=14,
        fg_color="#C9C7E9",
        hover_color="#C9C7E9",
        text_color="#FFFFFF",
        font=body_bold,
        state="disabled",
    )
    start_button.grid(row=9, column=0, sticky="ew", padx=20, pady=(18, 20))

    format_panel = ctk.CTkFrame(
        settings_card,
        width=330,
        height=178,
        fg_color=CARD,
        corner_radius=14,
        border_width=1,
        border_color="#D6D3FF",
    )
    format_panel.grid_columnconfigure((0, 1), weight=1)
    format_choices: dict[str, object] = {}
    for option_index, (option_key, option) in enumerate(FORMATS.items()):
        option_button = ctk.CTkButton(
            format_panel,
            text=option["label"],
            height=34,
            corner_radius=10,
            fg_color=ACCENT_SOFT if option_key == "original" else "transparent",
            hover_color=ACCENT_SOFT,
            text_color=ACCENT if option_key == "original" else TEXT,
            font=small_font,
            anchor="w",
            command=lambda key=option_key: choose_format(key),
        )
        option_button.grid(
            row=option_index // 2,
            column=option_index % 2,
            sticky="ew",
            padx=(8 if option_index % 2 == 0 else 4, 4 if option_index % 2 == 0 else 8),
            pady=(8 if option_index < 2 else 3, 8 if option_index >= len(FORMATS) - 2 else 3),
        )
        format_choices[option_key] = option_button

    result_card = ctk.CTkFrame(
        root,
        height=168,
        fg_color=CARD,
        corner_radius=20,
        border_width=1,
        border_color=BORDER,
    )
    result_card.grid(row=2, column=0, sticky="ew", padx=28, pady=(18, 24))
    result_card.grid_propagate(False)
    result_card.grid_columnconfigure(0, weight=1)
    result_card.grid_rowconfigure(2, weight=1)

    result_header = ctk.CTkFrame(result_card, fg_color="transparent")
    result_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 8))
    result_header.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(result_header, text="转换进度", text_color=TEXT, font=body_bold).grid(row=0, column=0, sticky="w")
    status_var = tk.StringVar(value="等待添加文件")
    ctk.CTkLabel(result_header, textvariable=status_var, text_color=MUTED, font=small_font).grid(row=0, column=1, sticky="e")

    progress = ctk.CTkProgressBar(
        result_card,
        height=8,
        corner_radius=4,
        fg_color="#EBECF2",
        progress_color=ACCENT,
    )
    progress.grid(row=1, column=0, sticky="ew", padx=20)
    progress.set(0)

    result_list = ctk.CTkScrollableFrame(
        result_card,
        height=60,
        fg_color=SURFACE,
        corner_radius=12,
        scrollbar_button_color="#D8DAE5",
        scrollbar_button_hover_color="#BFC3D2",
    )
    result_list.grid(row=2, column=0, sticky="nsew", padx=20, pady=(10, 16))
    result_list.grid_columnconfigure(0, weight=1)

    def clear_frame(frame: object) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def empty_row(parent: object, text: str) -> None:
        ctk.CTkLabel(parent, text=text, text_color=SUBTLE, font=small_font).grid(
            row=0, column=0, sticky="nsew", pady=16
        )

    def set_drop_style(active: bool) -> None:
        drop_card.configure(
            fg_color=DROP_ACTIVE if active else ACCENT_SOFT,
            border_color=ACCENT if active else "#C8C5FF",
        )
        drop_title.configure(text="松开即可加入转换列表" if active else "拖放 NCM 文件或文件夹")

    def update_start_button() -> None:
        if busy:
            start_button.configure(
                text="正在转换…",
                state="disabled",
                fg_color="#AAA7D7",
                hover_color="#AAA7D7",
            )
        elif inputs:
            start_button.configure(
                text=f"开始转换  ·  {len(inputs)} 项",
                state="normal",
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
            )
        else:
            start_button.configure(
                text="添加文件后即可开始",
                state="disabled",
                fg_color="#C9C7E9",
                hover_color="#C9C7E9",
            )

    def remove_path(path: Path) -> None:
        nonlocal inputs
        if busy:
            return
        inputs = [item for item in inputs if item != path]
        redraw_inputs()
        status_var.set(f"剩余 {len(inputs)} 项" if inputs else "等待添加文件")

    def redraw_inputs() -> None:
        clear_frame(input_list)
        queue_count.configure(text=f"{len(inputs)} 项")
        if not inputs:
            empty_row(input_list, "还没有文件，拖进来试试")
        for index, path in enumerate(inputs):
            row = ctk.CTkFrame(input_list, fg_color=CARD, corner_radius=11, border_width=1, border_color=BORDER)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 7))
            row.grid_columnconfigure(1, weight=1)
            badge = ctk.CTkLabel(
                row,
                text="夹" if path.is_dir() else "音",
                width=32,
                height=32,
                corner_radius=10,
                fg_color=ACCENT_SOFT,
                text_color=ACCENT,
                font=body_bold,
            )
            badge.grid(row=0, column=0, rowspan=2, padx=(10, 9), pady=9)
            ctk.CTkLabel(row, text=path.name, text_color=TEXT, font=small_font, anchor="w").grid(
                row=0, column=1, sticky="sew", pady=(8, 0)
            )
            location = "文件夹" if path.is_dir() else str(path.parent)
            ctk.CTkLabel(row, text=location, text_color=SUBTLE, font=ctk.CTkFont(size=10), anchor="w").grid(
                row=1, column=1, sticky="new", pady=(0, 8)
            )
            ctk.CTkButton(
                row,
                text="×",
                width=28,
                height=28,
                corner_radius=9,
                fg_color="transparent",
                hover_color=DANGER_SOFT,
                text_color=MUTED,
                font=ctk.CTkFont(size=17),
                command=lambda item=path: remove_path(item),
            ).grid(row=0, column=2, rowspan=2, padx=9)
            register_drop_tree(row)
        update_start_button()

    def add_paths(paths: Iterable[Path]) -> None:
        nonlocal inputs
        if busy:
            status_var.set("当前批次正在转换")
            return
        previous = len(inputs)
        inputs, rejected = merge_input_paths(inputs, paths)
        added = len(inputs) - previous
        redraw_inputs()
        if added:
            status_var.set(f"已加入 {added} 项，可以开始转换")
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

    def clear_inputs() -> None:
        nonlocal inputs
        if busy:
            return
        inputs = []
        redraw_inputs()
        status_var.set("列表已清空")

    def choose_output() -> None:
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            output_var.set(selected)

    def choose_format(target: str) -> None:
        format_var.set(FORMATS[target]["label"])
        hint_var.set(format_hint(target))
        for key, button in format_choices.items():
            selected = key == target
            button.configure(
                fg_color=ACCENT_SOFT if selected else "transparent",
                text_color=ACCENT if selected else TEXT,
            )
        format_panel.place_forget()

    def toggle_format_panel() -> None:
        if busy:
            return
        if format_panel.winfo_manager() == "place":
            format_panel.place_forget()
        else:
            format_panel.place(relx=0.5, y=94, anchor="n")
            format_panel.lift()

    def on_drop_enter(_: object) -> str:
        if not busy:
            set_drop_style(True)
        return COPY

    def on_drop_leave(_: object) -> str:
        set_drop_style(False)
        return COPY

    def on_drop(event: object) -> str:
        set_drop_style(False)
        try:
            raw_paths = root.tk.splitlist(event.data)
            add_paths(Path(item) for item in raw_paths)
        except (tk.TclError, AttributeError, ValueError) as exc:
            messagebox.showerror("无法读取拖入内容", str(exc))
        return COPY

    def register_drop_tree(widget: object) -> None:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<DropEnter>>", on_drop_enter)
        widget.dnd_bind("<<DropLeave>>", on_drop_leave)
        widget.dnd_bind("<<Drop>>", on_drop)
        for child in widget.winfo_children():
            register_drop_tree(child)

    def bind_click_tree(widget: object) -> None:
        widget.bind("<Button-1>", lambda _: add_files(), add="+")
        for child in widget.winfo_children():
            bind_click_tree(child)

    def set_controls_enabled(enabled: bool) -> None:
        if not enabled:
            format_panel.place_forget()
        state = "normal" if enabled else "disabled"
        for widget in interactive_widgets:
            widget.configure(state=state)
        update_start_button()

    def add_result(item: dict, ok: bool) -> None:
        row_index = len(result_list.winfo_children())
        row = ctk.CTkFrame(result_list, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        row.grid(row=row_index, column=0, sticky="ew", pady=(0, 6))
        row.grid_columnconfigure(1, weight=1)
        status = ctk.CTkLabel(
            row,
            text="成功" if ok else "失败",
            width=48,
            height=24,
            corner_radius=12,
            fg_color=SUCCESS_SOFT if ok else DANGER_SOFT,
            text_color=SUCCESS if ok else DANGER,
            font=small_font,
        )
        status.grid(row=0, column=0, rowspan=2, padx=10, pady=9)
        ctk.CTkLabel(
            row,
            text=Path(item["source"]).name,
            text_color=TEXT,
            font=small_font,
            anchor="w",
        ).grid(row=0, column=1, sticky="sew", pady=(7, 0))
        detail = item.get("output", "") if ok else item.get("error", "")
        if ok and item.get("notes"):
            detail += " · " + "；".join(item["notes"])
        ctk.CTkLabel(
            row,
            text=detail,
            text_color=SUBTLE,
            font=ctk.CTkFont(size=10),
            anchor="w",
        ).grid(row=1, column=1, sticky="new", padx=(0, 10), pady=(0, 7))

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
        clear_frame(result_list)
        progress.set(0)
        status_var.set(f"准备转换 {len(sources)} 个文件")
        busy = True
        set_controls_enabled(False)
        threading.Thread(
            target=worker,
            args=(
                sources,
                Path(output_var.get()).expanduser() if output_var.get().strip() else None,
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
                    add_result(item, ok)
                    progress.set(index / max(total, 1))
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

    clear_button.configure(command=clear_inputs)
    add_file_button.configure(command=add_files)
    add_folder_button.configure(command=add_folder)
    choose_output_button.configure(command=choose_output)
    format_display.configure(command=toggle_format_panel)
    format_arrow.configure(command=toggle_format_panel)
    start_button.configure(command=start)
    interactive_widgets.extend(
        [
            clear_button,
            add_file_button,
            add_folder_button,
            choose_output_button,
            output_entry,
            format_display,
            format_arrow,
            recursive_switch,
        ]
    )

    initial_paths = [Path(argument) for argument in sys.argv[1:] if argument != "--"]
    if initial_paths:
        add_paths(initial_paths)
    else:
        redraw_inputs()
    empty_row(result_list, "完成的转换会显示在这里")
    root.update_idletasks()
    register_drop_tree(root)
    bind_click_tree(drop_card)
    root.bind("<Return>", lambda _: start())
    if sys.platform == "darwin":
        root.bind("<Command-o>", lambda _: add_files())
    else:
        root.bind("<Control-o>", lambda _: add_files())
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
