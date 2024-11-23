from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Label, TabbedContent, TabPane, Select
from textual.containers import HorizontalGroup, VerticalScroll
from textual.validation import Validator, ValidationResult

from typing import Literal, List, Dict
from pathlib import Path
import subprocess
import yaml
from itertools import chain

import htcondor
import classad

CONDOR_OPTIONS = Path(__file__).parent / "condor_options"


class FileValidator(Validator):
    def validate(self, x: str) -> ValidationResult:
        """
        I hate that I can't just use a lambda lol
        #OOP_Gang
        """
        return (
            self.success()
            if Path(x).exists()
            else self.failure(f'File "{x}" not found.')
        )


class BoolValidator(Validator):
    def validate(self, x: str) -> ValidationResult:
        """
        I hate that I can't just use a lambda lol
        #OOP_Gang
        """
        return (
            self.success()
            if x.lower() in ["true", "false", "1", "0", "t", "f"]
            else self.failure(f'Bool "{x}" not found.')
        )


class EntryWindow(HorizontalGroup):

    def __init__(
        self,
        hint: str,
        condor_command: str,
        value: str = None,
        input_type: Literal[
            "text", "integer", "number", "file", "bool", "choice"
        ] = "text",
        validators: callable = None,
        options: List[str] = None,
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

        if input_type == "bool":
            _input_type = "text"
            if validators is None:
                validators = []
            validators.append(BoolValidator())

        if input_type == "choice":
            assert options is not None, f"{self.hint} needs options"
            self.input = Select(
                options=[(option, option) for option in options],
                id="prompt",
            )
        else:
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
            if self.input.is_valid
            else f"{self.condor_command}\n{event.validation_result.failures[-1].description}"
        )


class Peacock(App):

    CSS_PATH = "css/peacock.tcss"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("b", "show_tab('basic')", "basic"),
        ("a", "show_tab('advanced')", "advanced"),
        ("s", "save", "save"),
        ("S", "submit", "submit"),

    ]

    TITLE = "peacock"

    NOTIFICATION_TIMEOUT = 3

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.theme = "textual-dark"
        self.schedd = htcondor.Schedd()
        self.basic_options_scroll = self._get_basic_options_scroll()
        self.advanced_options_scroll = self._get_advanced_options_scroll()

        self.header = Header(icon="🦚")

    def compose(self) -> ComposeResult:
        yield self.header
        with TabbedContent(initial="basic"):
            with TabPane("basic options", id="basic"):
                yield self.basic_options_scroll
            with TabPane("advanced options", id="advanced"):
                yield self.advanced_options_scroll
        yield Footer()

    def action_save(
        self,
    ) -> None:
        # The first entry window *SHOULD* is the name of the job
        name = self.basic_options_scroll.children[0].value
        name = name if name else "condor"
        with open(f"{name}.job", "w") as f:
            for entry_window in chain(
                    self.basic_options_scroll.children,
                    self.advanced_options_scroll.children
                    ):
                if entry_window.value:
                    f.write(f"{entry_window.condor_command}={entry_window.value}\n")
        self.notify(f"Saved to {name}.job")

    def action_submit(self) -> None:
        # The first entry window *SHOULD* is the name of the job
        name = self.basic_options_scroll.children[0].value
        name = name if name else "condor"
        job = {}
        for entry_window in chain(
                self.basic_options_scroll.children,
                self.advanced_options_scroll.children
                ):
            if entry_window.value:
                job[entry_window.condor_command] = str(entry_window.value)
        hostname_job = htcondor.Submit(job)
        schedd_return: int = self.schedd.submit(hostname_job)
        if schedd_return:
            self.notify(f"Error submitting to {name} to the condor queue!")
        else:
            self.notify(f"Submitted to {name} to the condor queue!")

    def action_show_tab(self, tab: str) -> None:
        """Switch to a new tab."""
        self.get_child_by_type(TabbedContent).active = tab

    def _load_yaml(self, file: str) -> List[Dict[str, str]]:
        entry_windows = []
        with open(file, "r") as f:
            data = yaml.safe_load(f)
            for entry in data:
                entry_windows.append(
                    EntryWindow(
                        hint=entry["hint"],
                        condor_command=entry["condor_command"],
                        input_type=entry["input_type"],
                        value=entry["value"],
                        options=entry.get("options", None),
                    )
                )
        return entry_windows

    def _get_advanced_options_scroll(self):
        return VerticalScroll(*self._load_yaml(CONDOR_OPTIONS / "advanced_options.yaml"))

    def _get_basic_options_scroll(self):

        # Try to find the users current conda.sh script
        try:
            conda_sh_path = subprocess.check_output(
                "ls $(conda info --base)/etc/profile.d/conda.sh", shell=True, text=True
            ).strip()
        except subprocess.CalledProcessError as _:
            conda_sh_path = None

        # Try to find the users current conda environment
        try:
            current_env = subprocess.check_output(["conda", "env", "list"], text=True)
            for line in current_env.splitlines():
                if "*" in line:
                    active_env = line.split()[0]
                    break
            else:
                active_env = "base"
        except subprocess.CalledProcessError as _:
            active_env = None

        conda_sh_window = EntryWindow(
            hint="conda sh file",
            condor_command="source_file",
            input_type="text",
            value=conda_sh_path,
        )
        conda_env_window = EntryWindow(
            hint="conda environment",
            condor_command="conda_env",
            input_type="text",
            value=active_env,
        )
        return VerticalScroll(
            *(
                self._load_yaml(CONDOR_OPTIONS / "basic_options.yaml")
                # + [conda_sh_window, conda_env_window] # uncomment to add conda options
            )
        )


if __name__ == "__main__":
    app = Peacock()
    app.run()
