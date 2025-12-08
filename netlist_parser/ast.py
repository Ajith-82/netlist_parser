from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union, Any

@dataclass(kw_only=True)
class AstNode:
    """Base class for all AST nodes."""
    source_line: Optional[int] = None
    source_file: Optional[str] = None
    comments: List[str] = field(default_factory=list)

@dataclass
class Expression(AstNode):
    """Represents a mathematical expression or value."""
    expr_str: str

    def __repr__(self):
        return f"Expr('{self.expr_str}')"

@dataclass
class Parameter(AstNode):
    """Represents a parameter definition (param=value)."""
    name: str
    value: Union[str, float, Expression]

@dataclass
class Net(AstNode):
    """Represents a connection point (node)."""
    name: str

@dataclass
class Component(AstNode):
    """Base class for circuit components (R, C, M, X, etc.)."""
    name: str
    nodes: List[str]
    parameters: Dict[str, Union[str, float, Expression]] = field(default_factory=dict)
    model: Optional[str] = None

@dataclass
class Resistor(Component):
    value: Union[str, float, Expression] = 0.0

@dataclass
class Capacitor(Component):
    value: Union[str, float, Expression] = 0.0

@dataclass
class Inductor(Component):
    value: Union[str, float, Expression] = 0.0

@dataclass
class Mosfet(Component):
    model: str = ""  # Model is required for MOSFETs

@dataclass
class Bjt(Component):
    model: str = ""

@dataclass
class Diode(Component):
    model: str = ""

@dataclass
class VoltageSource(Component):
    dc_value: Union[str, float, Expression] = 0.0
    ac_value: Union[str, float, Expression] = 0.0

@dataclass
class CurrentSource(Component):
    dc_value: Union[str, float, Expression] = 0.0

@dataclass
class SubcktInstance(Component):
    """Instantiates a subcircuit (X element)."""
    subckt_name: str = "" 

@dataclass
class Subckt(AstNode):
    """Definition of a subcircuit."""
    name: str
    ports: List[str]
    components: List[Component] = field(default_factory=list)
    parameters: Dict[str, Union[str, float, Expression]] = field(default_factory=dict)
    
    def add_component(self, component: Component):
        self.components.append(component)

@dataclass
class Model(AstNode):
    """Represents a .MODEL statement."""
    name: str
    model_type: str
    parameters: Dict[str, Union[str, float, Expression]] = field(default_factory=dict)

@dataclass
class Circuit(AstNode):
    """Root node of the netlist."""
    name: str
    components: List[Component] = field(default_factory=list)
    subcircuits: List[Subckt] = field(default_factory=list)
    models: List[Model] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    
    def add_component(self, component: Component):
        self.components.append(component)
        
    def add_subckt(self, subckt: Subckt):
        self.subcircuits.append(subckt)

    def add_model(self, model: Model):
        self.models.append(model)
