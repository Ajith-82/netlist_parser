import re
import logging
import os
from typing import List, Optional, Tuple, Iterator, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from .base import BaseParser, Token, ParseError
from ..ast import (
    Circuit, Subckt, Resistor, Capacitor, Inductor, Mosfet, Bjt, Diode,
    VoltageSource, CurrentSource, SubcktInstance, Model, Component, Parameter
)
from ..utils import remove_comments, clean_line, tokenize_line

logger = logging.getLogger(__name__)

# Default number of worker threads for I/O operations
DEFAULT_IO_WORKERS = min(8, (os.cpu_count() or 4))

class SpiceTokenizer:
    """Handles SPICE line continuation and tokenization."""
    
    def __init__(self, content: str):
        self.lines = content.splitlines()
        self.current_line_idx = 0

    def get_logical_lines(self) -> Iterator[Tuple[int, str]]:
        """Yields (line_number, line_content) where logical lines are merged."""
        buffer = ""
        start_line = 0
        
        for i, line in enumerate(self.lines):
            line = remove_comments(line)
            line = line.rstrip() 
            
            if not line:
                continue
                
            if line.startswith('+'):
                # Continuation
                if buffer:
                    buffer += " " + line[1:].strip()
                else:
                    # Logic for leading + without previous line (error or ignore?)
                    # For now, treat as error or just start new line
                    buffer = line[1:].strip()
                    start_line = i + 1
            else:
                # Yield previous buffer
                if buffer:
                    yield start_line, buffer
                buffer = line.strip()
                start_line = i + 1
        
        if buffer:
            yield start_line, buffer

class SpiceParser(BaseParser):
    def __init__(self, num_threads: int = DEFAULT_IO_WORKERS):
        """Initialize parser with optional thread count for I/O operations."""
        self.num_threads = num_threads
        self._file_cache: Dict[str, str] = {}  # Cache for pre-loaded files

    def parse_file(self, filepath: str) -> Circuit:
        name = os.path.splitext(os.path.basename(filepath))[0]
        with open(filepath, 'r') as f:
            content = f.read()
        return self.parse(content, filename=filepath, circuit_name=name)

    def parse(self, content: str, filename: str = "<string>", circuit_name: str = "top") -> Circuit:
        self.circuit = Circuit(name=circuit_name)
        self.current_scope = self.circuit
        self.scope_stack = []
        self._file_cache = {}  # Reset cache for new parse

        # Track visited files to prevent cyclic includes
        # Store absolute paths
        abs_path = os.path.abspath(filename)
        self.visited_files = {abs_path}

        logger.info(f"Starting parse of '{filename}'")

        # A SPICE deck starts with a title line. Blank it (keeping line
        # numbers intact) so prose is not parsed as a device.
        first, sep, rest = content.partition('\n')
        if self._looks_like_title(first):
            logger.info(f"Ignoring title line: {first.strip()}")
            content = sep + rest

        # Pre-load include files in parallel for faster I/O
        if self.num_threads > 1:
            self._preload_includes(content, filename)
        self._process_content(content, filename)
        self._file_cache = {}  # Release pre-loaded file contents

        logger.info(f"Parse complete: {len(self.circuit.subcircuits)} subcircuits, "
                   f"{len(self.circuit.components)} top-level components, "
                   f"{len(self.circuit.models)} models")

        return self.circuit

    # Minimum token count for a line to be a plausible device statement
    _MIN_DEVICE_TOKENS = {'R': 4, 'C': 4, 'L': 4, 'M': 6, 'Q': 5, 'D': 4,
                          'X': 3, 'V': 4, 'I': 4}

    def _looks_like_title(self, line: str) -> bool:
        """
        Decide whether the first line of the top file is a SPICE title.

        CDL netlists and snippets often have no title, so the first line is
        kept when it is a comment, a dot command, or a plausible device
        statement. Anything else is treated as a title.
        """
        stripped = line.strip()
        if not stripped or stripped[0] in '.*+$':
            return False
        tokens = tokenize_line(remove_comments(stripped))
        if not tokens:
            return False
        min_tokens = self._MIN_DEVICE_TOKENS.get(tokens[0][0].upper())
        return min_tokens is None or len(tokens) < min_tokens

    def _process_content(self, content: str, file_path: str,
                         lib_section: Optional[str] = None) -> bool:
        """
        Parse content. If lib_section is given, only the lines between
        '.LIB <lib_section>' and the matching '.ENDL' are parsed.
        Returns False if a requested section was not found.
        """
        tokenizer = SpiceTokenizer(content)
        in_section = lib_section is None
        found = in_section

        for line_num, line in tokenizer.get_logical_lines():
            if lib_section is not None:
                head = line.split()
                cmd = head[0].upper()
                if not in_section:
                    if (cmd == '.LIB' and len(head) == 2 and
                            head[1].strip('"\'').lower() == lib_section):
                        in_section = found = True
                    continue
                if cmd == '.ENDL':
                    break
            try:
                self._parse_line(line, line_num, file_path)
            except Exception as e:
                print(f"Warning: Failed to parse line {line_num} in {file_path}: {line}. Error: {e}")
        return found

    def _parse_line(self, line: str, line_num: int, file_path: str):
        tokens = tokenize_line(line)
        if not tokens:
            return

        cmd = tokens[0].upper()

        if cmd.startswith('.'):
            self._parse_dot_command(cmd, tokens, line_num, file_path)
        else:
            self._parse_component(tokens[0], tokens, line_num)

    def _parse_dot_command(self, cmd: str, tokens: List[str], line_num: int, file_path: str):
        if cmd == '.SUBCKT' or cmd == '.MACRO':
            self._start_subckt(tokens, line_num, file_path)
        elif cmd == '.ENDS' or cmd == '.EOM':
            self._end_subckt()
        elif cmd == '.GLOBAL':
            self._parse_global(tokens)
        elif cmd == '.MODEL':
            self._parse_model(tokens)
        elif cmd == '.INCLUDE':
            if len(tokens) > 1:
                include_path = tokens[1].strip('"').strip("'")
                self._handle_include(include_path, file_path)
        elif cmd == '.LIB':
            if len(tokens) > 2:
                # .LIB 'file' section: include only that section of the file
                include_path = tokens[1].strip('"').strip("'")
                section = tokens[2].strip('"').strip("'").lower()
                self._handle_include(include_path, file_path, section)
            elif len(tokens) == 2:
                # .LIB name: either a whole-file include, or the start of a
                # section definition (closed by .ENDL), which needs no action.
                include_path = tokens[1].strip('"').strip("'")
                target = self._resolve_include_path(include_path, file_path)
                if os.path.isfile(target):
                    self._handle_include(include_path, file_path)
                else:
                    logger.debug(f"Library section '{include_path}' "
                                 f"in {file_path}")
        elif cmd == '.PARAM':
            self._parse_param(tokens)
        else:
            # Other commands (.TRAN, .OP, etc.) - ignore for netlist parsing
            pass

    def _resolve_include_path(self, include_path: str, current_file_path: str) -> str:
        """Resolve include path to absolute path."""
        if os.path.isabs(include_path):
            return os.path.abspath(include_path)
        current_dir = os.path.dirname(os.path.abspath(current_file_path))
        return os.path.abspath(os.path.join(current_dir, include_path))

    def _read_file(self, filepath: str) -> Optional[str]:
        """Read a file and return its contents, or None on error."""
        try:
            with open(filepath, 'r') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read file {filepath}: {e}")
            return None

    def _is_numeric_value(self, token: str) -> bool:
        """
        Check if a token looks like a numeric value (vs a model name).
        Numeric values: 1k, 10meg, 1.5u, 100, +5, -3.2e-6, etc.
        Model names: opppcres, nmos, pmos, etc.
        """
        if not token:
            return False
        # Remove leading +/- sign
        s = token.lstrip('+-')
        if not s:
            return False
        # Check if it starts with a digit or decimal point
        if s[0].isdigit() or s[0] == '.':
            return True
        return False

    def _is_parameter(self, token: str) -> bool:
        """Check if a token is a parameter (contains '=')."""
        return '=' in token

    def _extract_cdl_tokens(self, tokens: List[str]) -> Tuple[List[str], Dict[str, str], Optional[str]]:
        """
        Separate CDL comment-coded parameters ($-prefixed tokens) from a
        component line.

        - $[model]   -> device model name (e.g. '$[opppcres]')
        - $KEY=value -> parameter (e.g. '$SUB=VSS', '$W=1u')
        - $anything  -> start of an inline comment; rest of line is dropped

        Returns: (clean_tokens, cdl_params, cdl_model)
        """
        clean = []
        params = {}
        model = None
        for t in tokens:
            if t.startswith('$'):
                if t.startswith('$[') and t.endswith(']'):
                    model = t[2:-1]
                elif '=' in t:
                    k, v = t[1:].split('=', 1)
                    params[k] = v
                else:
                    break  # unrecognized $token: treat rest of line as comment
            else:
                clean.append(t)
        return clean, params, model

    def _parse_rcl_element(self, tokens, elem_type):
        """
        Parse R/C/L element handling 2 or 3 terminal devices.

        Formats supported:
        - N1 N2 value                 - 2 nodes + numeric value
        - N1 N2 model [params]        - 2 nodes + model name
        - N1 N2 N3 model [params]     - 3 nodes (with substrate) + model

        Returns: (nodes, value, model_name, val_idx)
        """
        # Default: assume 2 nodes
        token3 = tokens[3] if len(tokens) > 3 else "0"
        token4 = tokens[4] if len(tokens) > 4 else None

        if self._is_numeric_value(token3):
            # Classic: R N1 N2 value
            return tokens[1:3], token3, None, 4

        if self._is_parameter(token3):
            # R N1 N2 key=value ... - params only (model may come from $[...])
            return tokens[1:3], "0", None, 3

        # token3 is not numeric - could be model or third node
        if token4 and self._is_numeric_value(token4):
            # R N1 N2 model value
            return tokens[1:3], token4, token3, 5
        if token4 and not self._is_parameter(token4):
            # token4 exists and is not a param -> 3 nodes, token4 is model
            token5 = tokens[5] if len(tokens) > 5 else None
            if token5 and self._is_numeric_value(token5):
                # R N1 N2 N3 model value
                return tokens[1:4], token5, token4, 6
            return tokens[1:4], "0", token4, 5
        else:
            # 2 nodes, token3 is model
            return tokens[1:3], "0", token3, 4

    def _preload_includes(self, content: str, base_path: str):
        """
        Pre-scan content for include directives and load files in parallel.
        This speeds up I/O for netlists with many include files.
        """
        include_pattern = re.compile(
            r'^\s*\.(?:INCLUDE|LIB)\s+(?:"([^"\n]+)"|\'([^\'\n]+)\'|(\S+))',
            re.IGNORECASE | re.MULTILINE
        )

        # Find all includes in the content
        paths_to_load = []
        for match in include_pattern.finditer(content):
            inc_path = next(g for g in match.groups() if g).strip()
            resolved = self._resolve_include_path(inc_path, base_path)
            if resolved not in self._file_cache and os.path.exists(resolved):
                paths_to_load.append(resolved)

        if not paths_to_load:
            return

        logger.info(f"Pre-loading {len(paths_to_load)} include files "
                   f"using {self.num_threads} threads...")

        def load_file(path: str) -> tuple:
            content = self._read_file(path)
            return (path, content)

        # Parallel file reading
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = {executor.submit(load_file, p): p for p in paths_to_load}
            for future in as_completed(futures):
                path, file_content = future.result()
                if file_content is not None:
                    self._file_cache[path] = file_content
                    # Recursively pre-load includes from this file
                    self._preload_includes(file_content, path)

    def _handle_include(self, include_path: str, current_file_path: str,
                        lib_section: Optional[str] = None):
        # Resolve path
        target_path = self._resolve_include_path(include_path, current_file_path)

        # A library file may be read once per section, so track the pair
        visit_key = (target_path, lib_section) if lib_section else target_path
        if visit_key in self.visited_files:
            logger.debug(f"Skipping already visited include: {visit_key}")
            return  # Cycle or duplicate include detected

        if not os.path.exists(target_path):
            logger.warning(f"Include file not found: {target_path}")
            self.circuit.failed_includes.append(target_path)
            return

        self.visited_files.add(visit_key)
        logger.info(f"Processing include: {target_path}"
                    + (f" (section '{lib_section}')" if lib_section else ""))

        # Check cache first (populated by _preload_includes)
        if target_path in self._file_cache:
            content = self._file_cache[target_path]
        else:
            content = self._read_file(target_path)

        if content is None:
            return

        # Process the content
        found = self._process_content(content, target_path, lib_section)
        if not found:
            logger.warning(f"Library section '{lib_section}' not found in "
                           f"{target_path}")
            self.circuit.failed_includes.append(
                f"{target_path} (section '{lib_section}')")
            return
        if target_path not in self.circuit.includes:
            self.circuit.includes.append(target_path)

    def _parse_global(self, tokens: List[str]):
        """
        .GLOBAL / *.GLOBAL name... - names may be comma-separated and carry
        a CDL pad type suffix (:P power, :G ground).
        """
        for token in tokens[1:]:
            for name in token.split(','):
                if name[-2:].upper() in (':P', ':G'):
                    name = name[:-2]
                if name and name not in self.circuit.globals:
                    self.circuit.globals.append(name)

    def _parse_param(self, tokens: List[str]):
        # tokens[0] is .PARAM
        for t in tokens[1:]:
            if '=' in t:
                k, v = t.split('=', 1)
                # Helper to strip parens/quotes if desired, but for AST usually keep them
                # Just strip outer quotes if they exist? 
                # HSPICE: w='1+1'. AST: "1+1" or "'1+1'"?
                # Let's strip outer quotes for consistency if they are just grouping
                if v.startswith("'") and v.endswith("'"):
                    v = v[1:-1]
                
                if hasattr(self.current_scope, 'parameters'):
                    self.current_scope.parameters[k] = v

    def _start_subckt(self, tokens: List[str], line_num: Optional[int] = None,
                      file_path: Optional[str] = None):
        if len(tokens) < 2:
            raise ValueError("Invalid .SUBCKT definition")
        name = tokens[1]
        ports = tokens[2:]
        # Handle param definitions in subckt line (e.g. generic params)
        cleaned_ports = []
        params = {}
        
        # Simple param extraction from port list if they look like p=v
        for t in ports:
            if '=' in t:
                k, v = t.split('=', 1)
                params[k] = v
            else:
                cleaned_ports.append(t)

        subckt = Subckt(name=name, ports=cleaned_ports, parameters=params,
                        source_line=line_num, source_file=file_path)
        self.circuit.add_subckt(subckt)
        logger.debug(f"Found subcircuit: {name} with {len(cleaned_ports)} ports")

        # Push current scope
        self.scope_stack.append(self.current_scope)
        self.current_scope = subckt

    def _end_subckt(self):
        if self.scope_stack:
            self.current_scope = self.scope_stack.pop()

    def _parse_model(self, tokens: List[str]):
        if len(tokens) < 3:
            return 
        name = tokens[1]
        # '.model name type (k=v ...)': the parameter list may be wrapped in
        # parentheses, with or without a space after the type.
        match = re.match(r"([^\s(]+)\s*(.*)", ' '.join(tokens[2:]))
        mtype = match.group(1)
        body = match.group(2).strip()
        if body.startswith('('):
            body = body[1:]
            if body.count(')') > body.count('('):
                body = body[:body.rindex(')')] + body[body.rindex(')') + 1:]
        params = {}
        for t in tokenize_line(body):
            if '=' in t:
                k, v = t.split('=', 1)
                if v.startswith('(') and v.endswith(')'):
                    v = v[1:-1]
                params[k] = v

        model = Model(name=name, model_type=mtype, parameters=params)
        self.circuit.add_model(model)

    def _parse_component(self, name: str, tokens: List[str], line_num: int):
        # Separate CDL comment-coded parameters ($SUB=..., $[model], ...)
        tokens, cdl_params, cdl_model = self._extract_cdl_tokens(tokens)
        if not tokens:
            return

        # Basic SPICE first letter detection
        first_char = name[0].upper()
        
        # Helper to extract nodes and params
        # This is non-trivial for generic spice as node count varies.
        # We'll use basic heuristics.
        
        comp = None
        nodes = []
        params = {}
        model_name = None
        val_idx = -1 
        
        # Common pattern: Name Node1 Node2 ... [Value/Model] [Params]
        
        if first_char == 'R':
            # Resistor formats:
            # R N1 N2 value                    - 2 nodes + numeric value
            # R N1 N2 model [params]           - 2 nodes + model name
            # R N1 N2 N3 model [params]        - 3 nodes (with substrate) + model name
            nodes, value, model_name, val_idx = self._parse_rcl_element(tokens, 'R')
            comp = Resistor(name=name, nodes=nodes, value=value, model=model_name)

        elif first_char == 'C':
            # Capacitor formats (same as resistor)
            nodes, value, model_name, val_idx = self._parse_rcl_element(tokens, 'C')
            comp = Capacitor(name=name, nodes=nodes, value=value, model=model_name)

        elif first_char == 'L':
            # Inductor formats (same as resistor)
            nodes, value, model_name, val_idx = self._parse_rcl_element(tokens, 'L')
            comp = Inductor(name=name, nodes=nodes, value=value, model=model_name)
            
        elif first_char == 'M':
            # Mname D G S B Model [L=... W=...]
            # MOSFET usually has 4 nodes
            nodes = tokens[1:5]
            model_name = tokens[5]
            comp = Mosfet(name=name, nodes=nodes, model=model_name)
            val_idx = 6

        elif first_char == 'Q':
            # Qname C B E [S] Model [area] [params]
            # With a substrate node there are two names after C B E before
            # any numeric area or key=value parameter.
            n_nodes = 3
            if (len(tokens) > 5
                    and not self._is_parameter(tokens[5])
                    and not self._is_numeric_value(tokens[5])
                    and tokens[5].upper() != 'OFF'):
                n_nodes = 4
            nodes = tokens[1:1 + n_nodes]
            model_name = tokens[1 + n_nodes]
            comp = Bjt(name=name, nodes=nodes, model=model_name)
            val_idx = 2 + n_nodes

        elif first_char == 'D':
            # Dname N+ N- Model
            nodes = tokens[1:3]
            model_name = tokens[3]
            comp = Diode(name=name, nodes=nodes, model=model_name)
            val_idx = 4
            
        elif first_char == 'X':
            # Xname N1 N2 ... SubcktName
            # Xname N1 N2 ... / SubcktName params... (CDL style)
            
            if '/' in tokens:
                try:
                    slash_idx = tokens.index('/')
                    nodes = tokens[1:slash_idx]
                    # Subckt name is after slash
                    if slash_idx + 1 < len(tokens):
                        subckt_name = tokens[slash_idx + 1]
                        val_idx = slash_idx + 2
                    else:
                        raise ValueError("Missing subckt name after /")
                except ValueError:
                    # Logic error handling
                    return
            else:
                # Standard SPICE
                # The last non-param token is usually the subckt name
                # This is tricky. We'll scan from end for Params, then last is subckt
                
                # Simple heuristic: Split by '=' to find first param
                # The token BEFORE the first param is likely the subckt name
                # If no params, the last token is subckt name.
                
                param_start_index = len(tokens)
                for i, t in enumerate(tokens):
                     if '=' in t:
                         param_start_index = i
                         break
                
                subckt_name = tokens[param_start_index - 1]
                nodes = tokens[1:param_start_index - 1]
                val_idx = param_start_index
            
            comp = SubcktInstance(name=name, nodes=nodes, subckt_name=subckt_name)

        elif first_char == 'V':
             # Vname N+ N- [DC Value] [AC Value]
             nodes = tokens[1:3]
             # Simplify: take 4th token as DC value
             value = tokens[3] if len(tokens) > 3 else "0"
             comp = VoltageSource(name=name, nodes=nodes, dc_value=value)
             val_idx = 4

        elif first_char == 'I':
             nodes = tokens[1:3]
             value = tokens[3] if len(tokens) > 3 else "0"
             comp = CurrentSource(name=name, nodes=nodes, dc_value=value)
             val_idx = 4

        else:
            # Unsupported element type (E, F, G, H, K, J, ...)
            skipped = self.circuit.skipped_elements
            skipped[first_char] = skipped.get(first_char, 0) + 1
            logger.debug(f"Skipping unsupported element at line {line_num}: {name}")
             
        # Parse remaining tokens as parameters
        if comp:
            if cdl_model and not comp.model:
                comp.model = cdl_model
            comp.parameters.update(cdl_params)
            if val_idx != -1:
                remaining = tokens[val_idx:]
                for piece in remaining:
                    if '=' in piece:
                        k, v = piece.split('=', 1)
                        comp.parameters[k] = v
                    else:
                        # Handle standalone flags or unparsed params
                        if 'extra' not in comp.parameters:
                            comp.parameters['extra'] = []
                        if isinstance(comp.parameters.get('extra'), list):
                             comp.parameters['extra'].append(piece)

            comp.source_line = line_num
            self.current_scope.add_component(comp)
