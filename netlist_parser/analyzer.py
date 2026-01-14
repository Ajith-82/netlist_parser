from typing import Dict, List, Counter, Optional
import copy
from .ast import Circuit, Subckt, Component, SubcktInstance, Mosfet, Resistor, Capacitor, Inductor, Bjt, Diode, VoltageSource, CurrentSource

class NetlistAnalyzer:
    def __init__(self, circuit: Circuit, top_cell_name: Optional[str] = None):
        self.circuit = circuit
        self.top_cell_name = top_cell_name
        self.unresolved_subckts: set[str] = set()

        if self.top_cell_name:
            # Validate existence immediately
            if not any(s.name == self.top_cell_name for s in self.circuit.subcircuits):
                 raise ValueError(f"Top cell '{self.top_cell_name}' not found in netlist.")

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

    def _classify_component(self, comp: Component) -> str:
        """
        Classifies a component type. 
        For SubcktInstance, attempts to classify as primitive (Mosfet, Bjt, Diode) 
        based on heuristics (leaf cell, name, parameters).
        """
        if not isinstance(comp, SubcktInstance):
            return type(comp).__name__
            
        # It's a SubcktInstance. Check if it's a leaf/blackbox.
        subckt_def = next((s for s in self.circuit.subcircuits if s.name == comp.subckt_name), None)
        
        # If definition found and has components, it's a structural block, not a primitive.
        if subckt_def and subckt_def.components:
             return "SubcktInstance"
             
        # It's a leaf (empty subckt definition) or unresolved (treated as leaf).
        name_lower = comp.subckt_name.lower()
        
        # Check heuristics
        
        # MOSFET: Name contains fet/mos AND has W/L params
        if "fet" in name_lower or "mos" in name_lower:
            # Check for W and L params (case-insensitive keys)
            # Parameters might be in comp.parameters dict
            # We need to handle case-insensitivity of keys
            param_keys = {k.upper() for k in comp.parameters.keys()}
            if "W" in param_keys and "L" in param_keys:
                return "Mosfet"
                
        # BJT: Name contains bjt/npn/pnp
        if "bjt" in name_lower or "npn" in name_lower or "pnp" in name_lower:
            return "Bjt"
            
        # Diode: Name contains diode
        if "diode" in name_lower:
            return "Diode"
            
        return "SubcktInstance"

    def get_stats(self) -> Dict[str, int]:
        """Returns a count of all primitives in the top-level circuit (no flattening)."""
        stats = Counter()
        try:
            comps = self._get_root_components()
        except ValueError:
            return {}

        for comp in comps:
            stats[self._classify_component(comp)] += 1
        return dict(stats)

    def get_hierarchical_stats(self) -> Dict[str, int]:
        """Returns a count of all primitives in the flattened circuit (recursive)."""
        stats = Counter()
        try:
            flat_circuit = self.flatten()
            comps = flat_circuit.components
        except Exception:
            # Fallback or empty if flattening fails
            return {}

        for comp in comps:
            stats[self._classify_component(comp)] += 1
        return dict(stats)

    def print_hierarchy(self):
        """Prints an ASCII tree of the circuit hierarchy (subcircuit instances only)."""
        roots = self._get_root_components()
        root_name = self.top_cell_name if self.top_cell_name else self.circuit.name
        print(root_name)

        subckt_map = {s.name: s for s in self.circuit.subcircuits}

        def _print_level(components, prefix=""):
            # Filter for SubcktInstances only to keep tree readable
            instances = [c for c in components if isinstance(c, SubcktInstance)]
            # Sort by name for consistent output
            instances.sort(key=lambda x: x.name)

            for i, inst in enumerate(instances):
                is_last = (i == len(instances) - 1)
                connector = "└── " if is_last else "├── "
                print(f"{prefix}{connector}{inst.name} ({inst.subckt_name})")

                new_prefix = prefix + ("    " if is_last else "│   ")
                
                if inst.subckt_name in subckt_map:
                    _print_level(subckt_map[inst.subckt_name].components, new_prefix)
                # Else: it's an unresolved subckt or primitive (if we were printing them), nothing to recurse

        _print_level(roots)

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

                    # NEW: Trace empty subcircuits as leaf cells (primitives)
                    if not subckt_def.components:
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
            classification = self._classify_component(comp)
            if classification in ("Mosfet", "Bjt"):
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
            elif isinstance(comp, SubcktInstance):
                # Treat subckt name as model for black/leaf boxes
                model_counts[comp.subckt_name] += 1
                
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
