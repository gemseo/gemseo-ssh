from __future__ import annotations

from pathlib import Path

from gemseo.core.discipline import MDODiscipline


class DiscWithFiles(MDODiscipline):
    """A dummy discipline that handles files in inputs and outputs."""

    def __init__(self):
        super().__init__(grammar_type=self.GrammarType.SIMPLE)
        self.input_grammar.update_from_types({"in_file": str, "discipline": str})
        self.output_grammar.update_from_types({"out_file": str, "out_val": int})

    def _run(self):
        in_file_path = Path(self.local_data["in_file"])
        out_val = int(in_file_path.read_text()) + 1
        out_path = in_file_path.parent / "out_file.txt"
        out_path.write_text(str(out_val), encoding="utf8")

        self.local_data["out_val"] = out_val
        self.local_data["out_file"] = str(out_path)
