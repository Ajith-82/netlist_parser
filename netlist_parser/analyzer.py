from typing import Dict, List, Counter, Optional
import copy
from .ast import Circuit, Subckt, Component, SubcktInstance, Mosfet, Resistor, Capacitor, Inductor, Bjt, Diode, VoltageSource, CurrentSource

class NetlistAnalyzer:
    def __init__(self, circuit: Circuit, top_cell_name: Optional[str] = None):
        self.circuit = circuit
        self.top_cell_name = top_cell_name
        self.unresolved_subckts: set[str] = set()

    def _get_root_components(self) -> List[Component]:
        """Determines the starting components based on top_cell_name or auto-detection."""
        if self.top_cell_name:
            # User specified top cell
            subckt = next((s for s in self.circuit.subcircuits if s.name == self.top_cell_name), None)
            if not subckt:
                raise ValueError(f"Top cell '{self.top_cell_name}' not found in netlist.")
            # For a subcircuit root, we treat its components as the top level.
            # (Ports are treated as external nodes, same as auto-detect)
            return copy.deepcopy(subckt.components)
        
        if self.circuit.components:
            return self.circuit.components

        # Auto-detect
        top_subckt = self.find_top_cell()
        if top_subckt:
            return copy.deepcopy(top_subckt.components)
        
        return []

    def get_stats(self) -> Dict[str, int]:
        """Returns a count of all primitives in the top-level circuit (no flattening)."""
        stats = Counter()
        try:
            comps = self._get_root_components()
        except ValueError:
            return {}

        for comp in comps:
            stats[type(comp).__name__] += 1
        return dict(stats)

    def get_top_cells(self) -> List[str]:
        """Returns a list of names of all top-level subcircuits (defined but not instantiated)."""
        defined_subckts = {s.name for s in self.circuit.subcircuits}
        instantiated_subckts = set()
        
        for s in self.circuit.subcircuits:
            for comp in s.components:
                if isinstance(comp, SubcktInstance):
                    instantiated_subckts.add(comp.subckt_name)
                    
        roots = defined_subckts - instantiated_subckts
        return sorted(list(roots))

    def find_top_cell(self) -> Optional[Subckt]:
        """Heuristic to find the top-level subcircuit if the main circuit is empty."""
        roots = self.get_top_cells()
        
        if len(roots) == 1:
            root_name = roots[0]
            return next(s for s in self.circuit.subcircuits if s.name == root_name)
        
        # If multiple roots, we might want to pick the one with most components? 
        # Or just return None and let user specify (feature for later).
        # For this task, returning the first root found is a reasonable fallback 
        # if the list isn't empty, or just failing gracefully.
        if roots:
             # Just pick one for now or maybe filtering by name
             return next(s for s in self.circuit.subcircuits if s.name == roots[0])
             
        return None

    def flatten(self) -> Circuit:
        """
        Returns a new Circuit object with all subcircuits recursively flattened.
        Names of components and nodes are prefixed with the instance path.
        """
        flat_circuit = Circuit(name=self.circuit.name + "_flat")
        flat_circuit.models = copy.deepcopy(self.circuit.models)
        
        # Helper to recursively flatten
        def _flatten_instance(components: List[Component], path: str):
            for comp in components:
                if isinstance(comp, SubcktInstance):
                    # Find the subckt definition
                    subckt_def = next((s for s in self.circuit.subcircuits if s.name == comp.subckt_name), None)
                    if not subckt_def:
                        # Warning: Subckt not found, treating as a blacklist box
                        self.unresolved_subckts.add(comp.subckt_name)
                        # Copy as is or raise error? For now, keep as instance
                        new_comp = copy.deepcopy(comp)
                        new_comp.name = f"{path}.{comp.name}" if path else comp.name
                        flat_circuit.add_component(new_comp)
                        continue

                    # Map nodes
                    # Subckt ports map to Instance nodes
                    if len(subckt_def.ports) != len(comp.nodes):
                        # Warning: Port mismatch
                        pass
                    
                    node_map = {}
                    for port, node in zip(subckt_def.ports, comp.nodes):
                        node_map[port] = node # Map internal port name to external node name
                    
                    # Recursively flatten the subckt's components
                    # We need to map internal nodes to scoped names, UNLESS they hit a port
                    
                    instance_path = f"{path}.{comp.name}" if path else comp.name
                    
                    # Pre-process components for node renaming
                    # Create a deep copy of subckt components to modify
                    sub_components = copy.deepcopy(subckt_def.components)
                    
                    for sub_comp in sub_components:
                         new_nodes = []
                         for n in sub_comp.nodes:
                             if n in node_map:
                                 new_nodes.append(node_map[n]) # Connected to parent net
                             elif n == "0" or n.upper() == "GND":
                                 new_nodes.append("0") # Global GND
                             else:
                                 new_nodes.append(f"{instance_path}.{n}") # Internal net
                         sub_comp.nodes = new_nodes
                    
                    # Now recurse
                    _flatten_instance(sub_components, instance_path)

                else:
                    # Primitive component
                    new_comp = copy.deepcopy(comp)
                    new_comp.name = f"{path}.{comp.name}" if path else comp.name
                    flat_circuit.add_component(new_comp)

        try:
             start_components = self._get_root_components()
        except ValueError as e:
             # If specified top cell not found, return empty or raise?
             # For now let's raise so main() can handle it
             raise e

        _flatten_instance(start_components, "")
        
        return flat_circuit

    def get_transistor_count(self) -> int:
        """Returns total MOSFET + BJT count after flattening."""
        flat = self.flatten()
        count = 0
        for comp in flat.components:
            if isinstance(comp, (Mosfet, Bjt)):
                 count += 1
        return count

    def get_model_usage(self) -> Dict[str, int]:
        """Returns a dictionary of model names and their usage count in the flattened netlist."""
        flat = self.flatten()
        model_counts = Counter()
        
        for comp in flat.components:
            # Check if component has a 'model' attribute
            if hasattr(comp, 'model') and comp.model:
                model_counts[comp.model] += 1
                
        return dict(model_counts)
    
    def get_subckts_using_model(self, model_name: str) -> List[str]:
        """Returns a list of subcircuit names that directly instantiate the given model."""
        using_subckts = set()
        
        # Check in all subcircuit definitions
        for subckt in self.circuit.subcircuits:
            for comp in subckt.components:
                if hasattr(comp, 'model') and comp.model == model_name:
                    using_subckts.add(subckt.name)
                    break # Found usage in this subckt, move to next
                    
        # Also check top level if not empty (and not auto-using top cell)
        # Note: If find_top_cell logic is used, those are technically in a subckt.
        # But if the user parses a flat file, we check circuit.components.
        for comp in self.circuit.components:
             if hasattr(comp, 'model') and comp.model == model_name:
                 using_subckts.add(self.circuit.name) 
                 break

        return sorted(list(using_subckts))
