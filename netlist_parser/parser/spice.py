import re
from typing import List, Optional, Tuple, Iterator
from .base import BaseParser, Token, ParseError
from ..ast import (
    Circuit, Subckt, Resistor, Capacitor, Inductor, Mosfet, Bjt, Diode,
    VoltageSource, CurrentSource, SubcktInstance, Model, Component, Parameter
)
from ..utils import remove_comments, clean_line

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
    def parse_file(self, filepath: str) -> Circuit:
        import os
        name = os.path.splitext(os.path.basename(filepath))[0]
        with open(filepath, 'r') as f:
            content = f.read()
        return self.parse(content, filename=filepath, circuit_name=name)

    def parse(self, content: str, filename: str = "<string>", circuit_name: str = "top") -> Circuit:
        self.tokenizer = SpiceTokenizer(content)
        self.circuit = Circuit(name=circuit_name)
        self.current_scope = self.circuit # Can be Circuit or Subckt
        self.scope_stack = []

        for line_num, line in self.tokenizer.get_logical_lines():
            try:
                self._parse_line(line, line_num)
            except Exception as e:
                # In a real tool, we might want to log warnings and continue
                print(f"Warning: Failed to parse line {line_num}: {line}. Error: {e}")
        
        return self.circuit

    def _parse_line(self, line: str, line_num: int):
        from ..utils import tokenize_line
        tokens = tokenize_line(line)
        if not tokens:
            return

        cmd = tokens[0].upper()

        if cmd.startswith('.'):
            self._parse_dot_command(cmd, tokens, line_num)
        else:
            self._parse_component(cmd, tokens, line_num)

    def _parse_dot_command(self, cmd: str, tokens: List[str], line_num: int):
        if cmd == '.SUBCKT':
            self._start_subckt(tokens)
        elif cmd == '.ENDS':
            self._end_subckt()
        elif cmd == '.MODEL':
            self._parse_model(tokens)
        elif cmd == '.INCLUDE' or cmd == '.LIB':
            # TODO: Handle includes
            self.circuit.includes.append(" ".join(tokens[1:]))
        elif cmd == '.PARAM':
            self._parse_param(tokens)
        else:
            # Other commands (.TRAN, .OP, etc.) - ignore for netlist parsing
            pass

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

    def _start_subckt(self, tokens: List[str]):
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

        subckt = Subckt(name=name, ports=cleaned_ports, parameters=params)
        self.circuit.add_subckt(subckt)
        
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
        mtype = tokens[2]
        # Parse rest as params
        params = {}
        for t in tokens[3:]:
            if '=' in t:
                k, v = t.split('=', 1)
                # Helper to strip parens if present
                v = v.strip('()')
                params[k] = v
            # Handling models with parens like valid( level=1 ) is complex 
            # This is a basic implementation
        
        model = Model(name=name, model_type=mtype, parameters=params)
        self.circuit.add_model(model)

    def _parse_component(self, name: str, tokens: List[str], line_num: int):
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
            # Rname N1 N2 Value
            nodes = tokens[1:3]
            value = tokens[3] if len(tokens) > 3 else "0"
            comp = Resistor(name=name, nodes=nodes, value=value)
            val_idx = 4
            
        elif first_char == 'C':
             # Cname N1 N2 Value
            nodes = tokens[1:3]
            value = tokens[3] if len(tokens) > 3 else "0"
            comp = Capacitor(name=name, nodes=nodes, value=value)
            val_idx = 4

        elif first_char == 'L':
             # Lname N1 N2 Value
            nodes = tokens[1:3]
            value = tokens[3] if len(tokens) > 3 else "0"
            comp = Inductor(name=name, nodes=nodes, value=value)
            val_idx = 4
            
        elif first_char == 'M':
            # Mname D G S B Model [L=... W=...]
            # MOSFET usually has 4 nodes
            nodes = tokens[1:5]
            model_name = tokens[5]
            comp = Mosfet(name=name, nodes=nodes, model=model_name)
            val_idx = 6

        elif first_char == 'Q':
            # Qname C B E [S] Model
            # BJT usually 3 or 4 nodes
            # Heuristic: check if token 4 is a model or node
            # Ideally need to know if 4th token is model name. 
            # For now assume 3 nodes default.
            nodes = tokens[1:4]
            model_name = tokens[4]
            comp = Bjt(name=name, nodes=nodes, model=model_name)
            val_idx = 5

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
             
        # Parse remaining tokens as parameters
        if comp:
            if val_idx != -1:
                remaining = tokens[val_idx:]
                for piece in remaining:
                    if '=' in piece:
                        k, v = piece.split('=', 1)
                        comp.parameters[k] = v
                    else:
                        # Handle standalone flags or unparsed params
                        if 'params' not in comp.parameters:
                            comp.parameters['extra'] = []
                        if isinstance(comp.parameters.get('extra'), list):
                             comp.parameters['extra'].append(piece)

            comp.source_line = line_num
            self.current_scope.add_component(comp)
