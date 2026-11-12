"""Remove duplicated subcircuit definitions from a netlist file's text."""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Set

from .analyzer import DuplicateSubckt, NetlistAnalyzer
from .ast import Circuit, Subckt
from .parser.spice import SpiceParser
from .utils import remove_comments

_START = ('.SUBCKT', '.MACRO')
_END = ('.ENDS', '.EOM')


@dataclass
class DedupeResult:
    """Outcome of remove_duplicate_subckts()."""
    text: str                                   # Cleaned netlist text
    removed: List[Subckt] = field(default_factory=list)
    # Conflicting duplicates left in place because no 'keep' rule was given
    unresolved: List[DuplicateSubckt] = field(default_factory=list)
    # Redundant definitions that live in included files (not rewritten)
    in_includes: List[Subckt] = field(default_factory=list)


def _command(line: str) -> str:
    """First word of a physical line, upper-cased, ignoring comments."""
    words = remove_comments(line).split(None, 1)
    return words[0].upper() if words else ""


def _block_lines(lines: List[str], start: int) -> Optional[range]:
    """
    Line indices (0-based) of the subcircuit definition starting at `start`,
    through its closing .ENDS/.EOM and that line's continuation lines.
    Returns None if `start` is not a definition or it is never closed.
    """
    if start >= len(lines) or _command(lines[start]) not in _START:
        return None
    depth = 0
    for i in range(start, len(lines)):
        cmd = _command(lines[i])
        if cmd in _START:
            depth += 1
        elif cmd in _END:
            depth -= 1
            if depth == 0:
                end = i
                while (end + 1 < len(lines)
                       and remove_comments(lines[end + 1]).startswith('+')):
                    end += 1
                return range(start, end + 1)
    return None


def remove_duplicate_subckts(analyzer: NetlistAnalyzer, filepath: str,
                             content: str,
                             keep: Optional[str] = None) -> DedupeResult:
    """
    Cut redundant subcircuit definitions out of a netlist's text.

    Only `content` (the text of `filepath`, the file the circuit was parsed
    from) is edited; definitions in included files are reported, not removed.

    Args:
        analyzer: Analyzer for the circuit parsed from `filepath`.
        filepath: Path of the top netlist file.
        content: Text of that file.
        keep: None removes only identical duplicates. 'first' or 'last' also
              resolves conflicting duplicates, keeping that definition.

    Raises:
        ValueError: if a definition cannot be located in the text.
    """
    if keep not in (None, 'first', 'last'):
        raise ValueError("keep must be None, 'first' or 'last'")

    top = os.path.abspath(filepath)

    def in_top(subckt: Subckt) -> bool:
        return (subckt.source_file is not None
                and os.path.abspath(subckt.source_file) == top)

    result = DedupeResult(text=content)
    for dup in analyzer.get_duplicate_subckts():
        definitions = dup.definitions
        if dup.identical:
            # Any copy will do: keep one from an included file if there is
            # one, so that every copy in this file can be removed.
            outside = [d for d in definitions if not in_top(d)]
            if outside:
                survivor = outside[0]
            else:
                survivor = definitions[0] if keep == 'first' else definitions[-1]
        elif keep is None:
            result.unresolved.append(dup)
            continue
        else:
            survivor = definitions[0] if keep == 'first' else definitions[-1]

        for d in definitions:
            if d is survivor:
                continue
            (result.removed if in_top(d) else result.in_includes).append(d)

    if not result.removed:
        return result

    lines = content.splitlines(keepends=True)
    drop: Set[int] = set()
    for subckt in result.removed:
        block = _block_lines(lines, (subckt.source_line or 0) - 1)
        if block is None:
            raise ValueError(
                f"Could not locate the definition of '{subckt.name}' at "
                f"{filepath}:{subckt.source_line}")
        drop.update(block)

    result.text = "".join(l for i, l in enumerate(lines) if i not in drop)
    return result


def verify_dedupe(original: Circuit, result: DedupeResult, filepath: str,
                  case_sensitive: bool = False) -> Circuit:
    """
    Re-parse the cleaned text and check that only the removed definitions
    are gone. Returns the re-parsed circuit.

    Raises:
        ValueError: if the cleaned netlist does not match expectations.
    """
    # Parse under the original path so relative includes still resolve
    cleaned = SpiceParser(num_threads=1).parse(
        result.text, filename=filepath, circuit_name=original.name)

    def key(name: str) -> str:
        return name if case_sensitive else name.lower()

    def body_size(circuit: Circuit) -> int:
        return sum(len(s.components) for s in circuit.subcircuits)

    removed_body = sum(len(s.components) for s in result.removed)
    checks = [
        (len(cleaned.subcircuits)
         == len(original.subcircuits) - len(result.removed),
         "subcircuit count"),
        ({key(s.name) for s in cleaned.subcircuits}
         == {key(s.name) for s in original.subcircuits},
         "set of subcircuit names"),
        (len(cleaned.components) == len(original.components),
         "top-level component count"),
        (body_size(cleaned) == body_size(original) - removed_body,
         "component count inside subcircuits"),
    ]
    failed = [what for ok, what in checks if not ok]
    if failed:
        raise ValueError("Cleaned netlist failed verification: unexpected "
                         + ", ".join(failed))
    return cleaned
