"""The layers may only depend downwards (docs/architecture.md):

    api  ->  core / control  ->  handlers / data
             (schemas, config, constants, utils, observability: used by every layer)

So: data never imports api, core, control or handlers; handlers never import api or
control; core never imports api; control never imports api. Old migrations are left as
they ran (a migration file is never edited afterwards)."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
FORBIDDEN = {
    "data": ("src.api", "src.core", "src.control", "src.handlers"),
    "handlers": ("src.api", "src.control"),
    "core": ("src.api",),
    "control": ("src.api",),
}
EXEMPT = ("data/migrations/versions/",)


def imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return found


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layers_only_depend_downwards(layer: str) -> None:
    broken: list[str] = []
    for path in sorted((SRC / layer).rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if relative.startswith(EXEMPT):
            continue
        for module in imports(path):
            if module.startswith(FORBIDDEN[layer]):
                broken.append(f"{relative} imports {module}")
    assert broken == [], "\n".join(broken)
