from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Label, TabbedContent, TabPane, Select
from textual.containers import HorizontalGroup, VerticalScroll
from textual.validation import Validator, ValidationResult
from textual.reactive import reactive

from typing import Literal, List, Dict
from pathlib import Path
import subprocess
import yaml
import toml
import sys
from itertools import chain

import htcondor
import classad

CONDOR_OPTIONS = Path(__file__).parent / "condor_options"


class FileValidator(Validator):
    def validate(self, x: str) -> ValidationResult:
        return (
            self.success()
            if Path(x).exists()
            else self.failure(f'File "{x}" not found.')
        )


class BoolValidator(Validator):
    def validate(self, x: str) -> ValidationResult:
        return (
            self.success()
            if x.lower() in ["true", "false", "1", "0", "t", "f"]
            else self.failure(f'Bool "{x}" not found.')
        )


class QueuePage(VerticalScroll):

    queue: reactive[List[Dict[str, str]]] = reactive(lambda: [{}])

    def __init__(self, update_time: int, schedd: htcondor.Schedd) -> None:
        super().__init__()
        self.refresh_rate = update_time
        self.schedd = schedd
        self._jobs = self.get_queue_state()
        self.table_header = HorizontalGroup(
            *[Label(key, classes="q_box") for key in self._jobs[0].keys()]
        )
        self.queue_scroll = VerticalScroll(Label("No jobs in the queue"), id="queue")

    def on_mount(self) -> None:
        self.mount(self.queue_scroll)
        self.set_interval(self.refresh_rate, self.update_time)

    def compose(self) -> ComposeResult:
        yield self.table_header
        yield Label("No jobs in the queue", id="no_jobs")

    def watch_queue(self) -> None:

        try:
            no_jobs = self.get_child_by_id("no_jobs")
            no_jobs.remove()
        except Exception as e:
            pass

        try:
            queue_tab = self.get_child_by_id("queue")

            for child in queue_tab.children:
                child.remove()
            queue_tab.mount(self.table_header)
            for job in self.queue:
                queue_tab.mount(
                    HorizontalGroup(
                        *[Label(str(job[key]), classes="q_box") for key in job.keys()]
                    )
                )
        except Exception as e:
            self.notify(
                f"Error updating the queue page\n{e}",
                severity="error",
            )

    def get_queue_state(self) -> None:
        return self.schedd.query(
            projection=[
                "Owner",
                "JobStatus",
                "ClusterId",
            ]
        )

    def update_time(self) -> None:
        self.queue = self.get_queue_state()


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

    def update_value(self) -> None:
        self.label.update(
            f"{self.condor_command}: {self.value if self.value else 'None'}"
        )

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
        ("Q", "quit", "Quit"),
        ("b", "show_tab('basic')", "basic"),
        ("a", "show_tab('advanced')", "advanced"),
        ("q", "show_tab('queue')", "queue"),
        ("s", "save", "save"),
        ("S", "submit", "submit"),
    ]

    TITLE = "peacock"

    NOTIFICATION_TIMEOUT = 5

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.theme = "textual-dark"
        self.schedd = htcondor.Schedd()

        self.basic_options_scroll = VerticalScroll(
            *self._load_yaml(CONDOR_OPTIONS / "basic_options.yaml")
        )
        self.advanced_options_scroll = VerticalScroll(
            *self._load_yaml(CONDOR_OPTIONS / "advanced_options.yaml")
        )

        self.header = Header(icon="🦚")

        self.defaults = None
        self.config = self._get_config()

        # Get the queue page with a defualt update time of 5 seconds
        self.queue_page = QueuePage(
            self.config.get("update_time", 5),
            self.schedd,
        )

    def update_time(self) -> None:
        # assert -1 == 1, "TODO: call update on the queue page"
        pass

    def on_mount(self) -> None:
        config = self.config

        for key, value in config.items():
            if key == "theme":
                self.theme = value
            elif key == "primary_default":
                # allow the user to reference sub-dictionaries in the config file split by a period
                primary_default_name = value
                sub_dict = value.split(".")
                temp_dict = config
                for sub_key in sub_dict:
                    temp_dict = temp_dict.get(sub_key, None)
                    if not temp_dict:
                        self.notify(
                            f'Primary default "{primary_default_name}" not found in config file, not using specified defaults',
                            severity="error",
                        )
                        break
                self.defaults = temp_dict
            elif key == "update_time":
                self.update_time()
                self.set_interval(int(value), self.update_time)

        # if the user specifies a default to use from the command line,
        # prioritize that over the config file primary default
        if len(sys.argv) == 2:
            sub_dict = sys.argv[1].split(".")
            temp_dict = config
            for sub_key in sub_dict:
                temp_dict = temp_dict.get(sub_key, None)
                if not temp_dict:
                    self.notify(
                        f'Default "{sys.argv[1]}" not found in config file, not using specified defaults',
                        severity="error",
                    )
                    break
            defaults = temp_dict
            if defaults:
                self.defaults = defaults
                self.notify(f'Using "{sys.argv[1]}" defaults')
            else:
                self.notify(
                    f'Default "{sys.argv[1]}" not found in config file, not using specified defaults',
                    severity="error",
                )
        elif len(sys.argv) > 2:
            self.notify(
                "Too many arguments, ignoring all but the first", severity="error"
            )
        elif len(sys.argv) == 1 and self.defaults:
            self.notify(f'Using primary default "{primary_default_name}"')

        if self.defaults:
            for entry_window in chain(
                self.basic_options_scroll.children,
                self.advanced_options_scroll.children,
            ):
                if entry_window.condor_command in self.defaults.keys():
                    entry_window.value = self.defaults[entry_window.condor_command]
                    entry_window.update_value()

    def compose(self) -> ComposeResult:
        yield self.header
        with TabbedContent(initial="basic"):
            with TabPane("basic options", id="basic"):
                yield self.basic_options_scroll
            with TabPane("advanced options", id="advanced"):
                yield self.advanced_options_scroll
            with TabPane("queue", id="queue"):
                yield self.queue_page
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
                self.advanced_options_scroll.children,
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
            self.basic_options_scroll.children, self.advanced_options_scroll.children
        ):
            if entry_window.value:
                job[entry_window.condor_command] = str(entry_window.value)
        hostname_job = htcondor.Submit(job)
        try:
            schedd_return: int = self.schedd.submit(hostname_job)
            # FIXME: This is broken, I don't know what shedd_return is supposed to be lol
            # if schedd_return:
            #     self.notify(
            #         f"Error submitting to {name} to the condor queue!\n{schedd_return}",
            #         severity="error",
            #     )
            # else:
            self.notify(f"Submitted to \"{name}\" to the condor queue!")
        except Exception as e:
            self.notify(
                f"Error submitting to \"{name}\" to the condor queue!\n{e}",
                severity="error",
            )

    def action_show_tab(self, tab: str) -> None:
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

    def _get_config(
        self,
    ) -> None:
        peacock_config = Path.home() / ".config/peacock/config.toml"
        if peacock_config.exists():
            with open(peacock_config, "r") as f:
                config = toml.load(f)
        return config


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print(
            "Usage:\n",
            "\tpeacock [default]\n\n",
            "default:\n",
            "\tThe default values to use from the config file, help on configuring this is in the config files.\n",
            "Example:\n",
            "\tpeacock primary_default\n",
            "\nIf no default is specified, the primary default from the config file will be used.",
            sep="",
        )
    else:
        app = Peacock()
        app.run()


if __name__ == "__main__":
    main()
