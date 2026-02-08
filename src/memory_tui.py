"""保護記憶管理TUI - textualベースのターミナルUI"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Label, Static

from memory_store import MemoryStore


def get_store() -> MemoryStore:
    db_path = Path(__file__).parent.parent / "data" / "memories.db"
    return MemoryStore(db_path)


def truncate(text: str, length: int = 30) -> str:
    text = text.replace("\n", " ")
    if len(text) > length:
        return text[:length] + "..."
    return text


class ConfirmScreen(ModalScreen[bool]):
    """一括unprotect確認ダイアログ"""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 50;
        height: 7;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #confirm-dialog Label {
        width: 100%;
        content-align: center middle;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"{self.count}件の記憶を保護解除しますか？")
            yield Label("[y] Yes  [n] No")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class MemoryTUIApp(App):
    """保護記憶管理TUI"""

    TITLE = "Protected Memory Manager"

    CSS = """
    #memory-list {
        height: 70%;
    }
    #preview {
        height: 30%;
        border-top: solid $accent;
        padding: 0 1;
        overflow-y: auto;
    }
    #sort-status {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_check", "Check", show=False),
        Binding("s", "toggle_sort", "Sort"),
        Binding("a", "toggle_all", "Select All"),
        Binding("u", "unprotect", "Unprotect"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.store = get_store()
        self.sort_by = "created"
        self.checked: set[str] = set()
        self.memories: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(f"Sort: date (created DESC)", id="sort-status")
        yield DataTable(id="memory-list")
        yield Static("", id="preview")
        yield Footer()

    def on_mount(self) -> None:
        self.load_memories()

    def load_memories(self) -> None:
        self.memories = self.store.get_protected_memories(order_by=self.sort_by)
        table = self.query_one("#memory-list", DataTable)
        table.clear(columns=True)
        table.cursor_type = "row"
        table.add_columns("", "Date", "Trigger", "Score")

        for mem in self.memories:
            check = "☑" if mem["id"] in self.checked else "☐"
            date = mem["created"][:10]
            trigger = truncate(mem["trigger"], 30)
            score = f'{mem["retention_score"]:.0f}' if mem["retention_score"] is not None else "-"
            table.add_row(check, date, trigger, score, key=mem["id"])

        # プレビュー更新
        if self.memories:
            self.update_preview(0)
        else:
            self.query_one("#preview", Static).update("(保護記憶なし)")

    def update_preview(self, index: int) -> None:
        if 0 <= index < len(self.memories):
            mem = self.memories[index]
            preview = self.query_one("#preview", Static)
            trigger_text = mem['trigger'].replace('\n', ' ')
            content_text = mem['content'].replace('\n', ' ')
            preview.update(
                f"[bold]trigger:[/bold]\n{trigger_text}\n\n"
                f"[bold]content:[/bold]\n{content_text}"
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.update_preview(event.cursor_row)

    def action_toggle_check(self) -> None:
        table = self.query_one("#memory-list", DataTable)
        if not self.memories:
            return
        row_idx = table.cursor_row
        mem_id = self.memories[row_idx]["id"]

        if mem_id in self.checked:
            self.checked.discard(mem_id)
        else:
            self.checked.add(mem_id)

        check = "☑" if mem_id in self.checked else "☐"
        table.update_cell_at((row_idx, 0), check)

    def action_toggle_sort(self) -> None:
        if self.sort_by == "created":
            self.sort_by = "retention_score"
            label = "Sort: score (retention_score DESC)"
        else:
            self.sort_by = "created"
            label = "Sort: date (created DESC)"
        self.query_one("#sort-status", Label).update(label)
        self.load_memories()

    def action_toggle_all(self) -> None:
        if not self.memories:
            return
        all_ids = {m["id"] for m in self.memories}
        if self.checked == all_ids:
            self.checked.clear()
        else:
            self.checked = all_ids
        self.load_memories()

    def action_unprotect(self) -> None:
        if not self.checked:
            return

        def on_confirm(result: bool) -> None:
            if result:
                for mem_id in self.checked:
                    self.store.update_memory(mem_id, {"protected": False})
                self.checked.clear()
                self.load_memories()

        self.push_screen(ConfirmScreen(len(self.checked)), on_confirm)


def main() -> None:
    app = MemoryTUIApp()
    app.run()


if __name__ == "__main__":
    main()
