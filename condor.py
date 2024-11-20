from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Label
from textual.containers import HorizontalGroup, VerticalScroll
from textual.validation import Validator, ValidationResult

from typing import Literal
from pathlib import Path


class FileValidator(Validator):
    def validate(self, x: str) -> ValidationResult:
        """
        I hate that I can't just use a lambda lol
        #OOP_Gang
        """
        return self.success() if Path(x).exists() else self.failure("File not found.")


class EntryWindow(HorizontalGroup):

    def __init__(
        self,
        hint: str,
        condor_command: str,
        value: str = None,
        input_type: Literal["text", "integer", "number", "file"] = "text",
        validators: callable = None,
    ) -> None:
        super().__init__()
        self.hint = hint
        self.value = value
        self.condor_command = condor_command
        self.input_type = input_type

        _input_type = input_type
        if input_type == "file":
            _input_type = "text"
            if validators is None:
                validators = []
            # just a way to check if the user hands us a real file
            validators.append(FileValidator())

        self.input = Input(
            placeholder=self.hint,
            id="prompt",
            type=_input_type,
            validators=validators,
        )
        self.label = Label(
            f"{self.condor_command}: {self.value if self.value else 'None'}", id="value"
        )

    def compose(self) -> ComposeResult:
        yield self.input
        yield self.label

    @on(Input.Submitted)
    def save_args(self, event: Input.Submitted) -> None:
        if self.input_type == "file":
            self.value = Path(event.value).absolute()
        else:
            self.value = event.value
        self.label.update(
            f"{self.condor_command}: {self.value if self.value else 'None'}"
        )


class CondorTUI(App):

    CSS_PATH = "condor.tcss"

    BINDINGS = [
        ("d", "action_toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
        ("a", "advanced_options", "Advanced options"),
        ("s", "save", "save"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.theme = "textual-light"
        self.vertical_scroll = self._get_vertical_scroll()

        class Dummy:
            children = []

        self.advanced_options = Dummy()

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.vertical_scroll
        yield Footer()

    def action_toggle_dark(
        self,
    ) -> None:
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )

    def action_save(
        self,
    ) -> None:
        with open(f"{self.vertical_scroll.children[0].value}.job", "w") as f:
            for entry_window in (
                self.vertical_scroll.children # + self.advanced_options.children
            ):
                f.write(f"{entry_window.condor_command}={entry_window.value}\n")

    def _get_vertical_scroll(self):
        return VerticalScroll(
            EntryWindow(
                hint="name of job",
                condor_command="name",
                input_type="text",
                value="job",
            ),
            EntryWindow(
                hint="file to run",
                condor_command="executable",
                input_type="file",
                value=None,
            ),
            EntryWindow(
                hint="num cpus",
                condor_command="request_cpus",
                input_type="integer",
                value=1,
            ),
            EntryWindow(
                hint="num gpus",
                condor_command="request_gpus",
                input_type="integer",
                value=1,
            ),
            EntryWindow(
                hint="max jobs",
                condor_command="queue",
                input_type="integer",
                value=1,
            ),
        )


if __name__ == "__main__":
    app = CondorTUI()
    app.run()
