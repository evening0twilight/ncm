"""Small local Tk desktop interface. File access and conversion stay on this computer."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from .transcode import FORMATS
from .workflow import collect_sources, run_batch


def target_from_label(label: str) -> str:
    for key, value in FORMATS.items():
        if value["label"] == label:
            return key
    raise ValueError(f"未知目标格式：{label}")


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise SystemExit("桌面界面需要 Tk。macOS Homebrew Python 请运行：brew install python-tk@3.14") from exc

    root = tk.Tk()
    root.title("NCM 本地音频转换")
    root.geometry("1040x680")
    root.minsize(760, 520)
    messages: queue.Queue[tuple] = queue.Queue()
    inputs: list[Path] = []
    busy = False

    mainframe = ttk.Frame(root, padding=16)
    mainframe.pack(fill="both", expand=True)
    ttk.Label(mainframe, text="NCM 本地音频转换", font=("Helvetica", 18, "bold")).pack(anchor="w")
    ttk.Label(mainframe, text="默认原样恢复，不重新编码。选择其他目标格式会用本机 FFmpeg 转码；源文件始终保留。", wraplength=980).pack(anchor="w", pady=(4, 12))

    controls = ttk.Frame(mainframe)
    controls.pack(fill="x")
    input_tree = ttk.Treeview(mainframe, columns=("path",), show="headings", height=7)
    input_tree.heading("path", text="输入文件或文件夹")
    input_tree.column("path", width=900)

    def redraw_inputs() -> None:
        input_tree.delete(*input_tree.get_children())
        for path in inputs:
            input_tree.insert("", "end", values=(str(path),))

    def add_files() -> None:
        for item in filedialog.askopenfilenames(title="选择 NCM 文件", filetypes=[("NCM 音频", "*.ncm"), ("所有文件", "*")]):
            path = Path(item)
            if path not in inputs:
                inputs.append(path)
        redraw_inputs()

    def add_folder() -> None:
        selected = filedialog.askdirectory(title="选择包含 NCM 的文件夹")
        if selected and Path(selected) not in inputs:
            inputs.append(Path(selected))
            redraw_inputs()

    def remove_selected() -> None:
        selected = {input_tree.item(item, "values")[0] for item in input_tree.selection()}
        inputs[:] = [item for item in inputs if str(item) not in selected]
        redraw_inputs()

    buttons = []
    for label, action in (("添加文件…", add_files), ("添加文件夹…", add_folder), ("移除选中", remove_selected)):
        button = ttk.Button(controls, text=label, command=action)
        button.pack(side="left", padx=(0, 8))
        buttons.append(button)
    recursive = tk.BooleanVar(value=True)
    recursive_button = ttk.Checkbutton(controls, text="搜索子文件夹", variable=recursive)
    recursive_button.pack(side="left", padx=8)
    input_tree.pack(fill="x", pady=(8, 14))

    options = ttk.Frame(mainframe)
    options.pack(fill="x")
    ttk.Label(options, text="输出目录").grid(row=0, column=0, sticky="w")
    output_var = tk.StringVar()
    output_entry = ttk.Entry(options, textvariable=output_var)
    output_entry.grid(row=0, column=1, sticky="ew", padx=8)
    ttk.Button(options, text="选择…", command=lambda: output_var.set(filedialog.askdirectory(title="选择输出目录") or output_var.get())).grid(row=0, column=2)
    ttk.Label(options, text="留空：每个源文件旁的 recovered 文件夹").grid(row=1, column=1, sticky="w")
    ttk.Label(options, text="目标格式").grid(row=2, column=0, sticky="w", pady=(12, 0))
    format_var = tk.StringVar(value=FORMATS["original"]["label"])
    format_box = ttk.Combobox(options, textvariable=format_var, values=[item["label"] for item in FORMATS.values()], state="readonly", width=38)
    format_box.grid(row=2, column=1, sticky="w", padx=8, pady=(12, 0))
    options.columnconfigure(1, weight=1)

    progress = ttk.Progressbar(mainframe, mode="determinate")
    progress.pack(fill="x", pady=(16, 4))
    status_var = tk.StringVar(value="等待选择文件")
    ttk.Label(mainframe, textvariable=status_var).pack(anchor="w")
    result_tree = ttk.Treeview(mainframe, columns=("status", "source", "detail"), show="headings", height=11)
    for column, title, width in (("status", "结果", 70), ("source", "源文件", 320), ("detail", "输出或失败原因", 560)):
        result_tree.heading(column, text=title)
        result_tree.column(column, width=width, stretch=column != "status")
    result_tree.pack(fill="both", expand=True, pady=(10, 0))

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
        if busy:
            return
        if not inputs:
            messagebox.showinfo("没有输入", "请先添加 NCM 文件或文件夹。")
            return
        sources, failures = collect_sources(inputs, recursive.get())
        if not sources and not failures:
            messagebox.showinfo("没有输入", "未找到 NCM 文件。")
            return
        result_tree.delete(*result_tree.get_children())
        progress.configure(maximum=max(len(sources), 1), value=0)
        status_var.set(f"准备处理 {len(sources)} 个文件")
        busy = True
        for button in buttons:
            button.configure(state="disabled")
        start_button.configure(state="disabled")
        format_box.configure(state="disabled")
        recursive_button.configure(state="disabled")
        threading.Thread(
            target=worker,
            args=(sources, Path(output_var.get()) if output_var.get().strip() else None, target_from_label(format_var.get()), failures),
            daemon=True,
        ).start()

    def poll() -> None:
        nonlocal busy
        try:
            while True:
                event = messages.get_nowait()
                if event[0] == "start":
                    _, index, total, source = event
                    status_var.set(f"正在处理 {index}/{total}：{Path(source).name}")
                elif event[0] == "result":
                    _, index, total, item, ok = event
                    detail = item.get("output", "") if ok else item.get("error", "")
                    if ok and item.get("notes"):
                        detail += " | " + "; ".join(item["notes"])
                    result_tree.insert("", "end", values=("成功" if ok else "失败", item["source"], detail))
                    progress.configure(value=index)
                    status_var.set(f"已处理 {index}/{total} 个文件")
                elif event[0] in ("done", "fatal"):
                    busy = False
                    for button in buttons:
                        button.configure(state="normal")
                    start_button.configure(state="normal")
                    format_box.configure(state="readonly")
                    recursive_button.configure(state="normal")
                    status_var.set(f"完成：成功 {event[1]}，失败 {event[2]}" if event[0] == "done" else "处理失败：" + event[1])
        except queue.Empty:
            pass
        root.after(100, poll)

    start_button = ttk.Button(mainframe, text="开始转换", command=start)
    start_button.pack(anchor="e", pady=(12, 0))
    def close() -> None:
        if busy:
            messagebox.showinfo("正在处理", "请等待当前批量处理完成后再关闭窗口。")
        else:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
