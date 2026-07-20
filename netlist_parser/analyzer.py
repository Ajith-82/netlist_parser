from typing import Dict, List, Counter, Optional
import copy
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from .ast import Circuit, Subckt, Component, SubcktInstance, Mosfet, Resistor, Capacitor, Inductor, Bjt, Diode, VoltageSource, CurrentSource

logger = logging.getLogger(__name__)

# Default number of worker threads (can be overridden)
DEFAULT_WORKERS = min(8, (os.cpu_count() or 4))

class NetlistAnalyzer:
    def __init__(self, circuit: Circuit, top_cell_name: Optional[str] = None):
        self.circuit = circuit
        self.top_cell_name = top_cell_name
        self.unresolved_subckts: set[str] = set()

        logger.info(f"Initializing analyzer for circuit: {circuit.name}")
        if self.top_cell_name:
            logger.info(f"Using specified top cell: {self.top_cell_name}")
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
            logger.debug(f"Using user-specified top cell: {self.top_cell_name} "
                        f"({len(subckt.components)} direct components)")
            return copy.deepcopy(subckt.components)

        if self.circuit.components:
            logger.debug(f"Using top-level components ({len(self.circuit.components)} components)")
            return self.circuit.components

        # Auto-detect
        top_subckt = self.find_top_cell()
        if top_subckt:
            logger.debug(f"Using auto-detected top cell: {top_subckt.name} "
                        f"({len(top_subckt.components)} direct components)")
            return copy.deepcopy(top_subckt.components)

        logger.warning("No top cell found - returning empty component list")
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

        if len(roots) == 0:
            return None

        if len(roots) == 1:
            root_name = roots[0]
            logger.info(f"Single top cell found: {root_name}")
            return next(s for s in self.circuit.subcircuits if s.name == root_name)

        # Multiple roots - pick the one with the most components (hierarchical complexity)
        # This helps avoid picking small primitives from standard cell libraries
        logger.warning(f"Multiple top cells found ({len(roots)}). "
                      f"Use --top-cell to specify. Attempting auto-detection...")

        subckt_map = {s.name: s for s in self.circuit.subcircuits}

        def count_components(subckt_name: str, visited: set) -> int:
            """Recursively count components in a subcircuit hierarchy."""
            if subckt_name in visited or subckt_name not in subckt_map:
                return 0
            visited.add(subckt_name)
            subckt = subckt_map[subckt_name]
            count = len(subckt.components)
            for comp in subckt.components:
                if isinstance(comp, SubcktInstance):
                    count += count_components(comp.subckt_name, visited)
            return count

        def count_for_root(root_name: str) -> tuple:
            """Thread worker: count components for a single root."""
            count = count_components(root_name, set())
            return (root_name, count)

        # Use thread pool for parallel counting when many candidates
        best_root = None
        best_count = -1

        if len(roots) > 100:
            # Parallel processing for large number of candidates
            logger.info(f"Using {DEFAULT_WORKERS} threads for top cell detection...")
            with ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as executor:
                futures = {executor.submit(count_for_root, r): r for r in roots}
                for future in as_completed(futures):
                    root_name, count = future.result()
                    logger.debug(f"Top cell candidate: {root_name} ({count} components)")
                    if count > best_count:
                        best_count = count
                        best_root = root_name
        else:
            # Sequential for small number of candidates
            for root_name in roots:
                count = count_components(root_name, set())
                logger.debug(f"Top cell candidate: {root_name} ({count} components)")
                if count > best_count:
                    best_count = count
                    best_root = root_name

        if best_root:
            logger.info(f"Auto-selected top cell: {best_root} ({best_count} components)")
            return subckt_map[best_root]

        return None

    def flatten(self) -> Circuit:
        """
        Returns a new Circuit object with all subcircuits recursively flattened.
        Names of components and nodes are prefixed with the instance path.
        """
        logger.info("Starting circuit flattening...")
        flat_circuit = Circuit(name=self.circuit.name + "_flat")
        flat_circuit.models = copy.deepcopy(self.circuit.models)
        
        # Helper to recursively flatten
        def _flatten_instance(components: List[Component], path: str):
            for comp in components:
                if isinstance(comp, SubcktInstance):
                    # Find the subckt definition
                    subckt_def = next((s for s in self.circuit.subcircuits if s.name == comp.subckt_name), None)
                    if not subckt_def:
                        # Warning: Subckt not found, treating as a black box
                        self.unresolved_subckts.add(comp.subckt_name)
                        logger.debug(f"Unresolved subcircuit: {comp.subckt_name}")
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

        logger.info(f"Flattening complete: {len(flat_circuit.components)} components")
        if self.unresolved_subckts:
            logger.warning(f"Unresolved subcircuits: {', '.join(self.unresolved_subckts)}")

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

    def get_model_usage(self, case_insensitive: bool = True) -> Dict[str, int]:
        """
        Returns a dictionary of model names and their usage count in the flattened netlist.

        Args:
            case_insensitive: If True (default), normalize model names to lowercase
                             since SPICE is case-insensitive.
        """
        flat = self.flatten()
        model_counts = Counter()

        for comp in flat.components:
            # Check if component has a 'model' attribute
            if hasattr(comp, 'model') and comp.model:
                name = comp.model.lower() if case_insensitive else comp.model
                model_counts[name] += 1
            elif isinstance(comp, SubcktInstance):
                # Treat subckt name as model for black/leaf boxes
                name = comp.subckt_name.lower() if case_insensitive else comp.subckt_name
                model_counts[name] += 1

        return dict(model_counts)

    def get_all_models(self, case_insensitive: bool = True) -> List[str]:
        """
        Extract all unique model names from the netlist without flattening.

        This method scans all subcircuits and top-level components to find
        all model names, regardless of hierarchy. It's faster than get_model_usage()
        for large designs since it doesn't require flattening.

        Args:
            case_insensitive: If True (default), normalize model names to lowercase
                             since SPICE is case-insensitive.

        Returns:
            Sorted list of unique model names found in the netlist.
        """
        models = set()
        subckt_map = {s.name: s for s in self.circuit.subcircuits}

        def extract_model(comp):
            """Extract model name from a component if it has one."""
            if hasattr(comp, 'model') and comp.model:
                return comp.model.lower() if case_insensitive else comp.model
            if isinstance(comp, SubcktInstance):
                # CDL primitives are often X-instances of leaf cells
                # (e.g. "XM1 d g s b pmos_1p5 W=... L=..."). Treat instances
                # of empty or undefined subcircuits as devices.
                sub_def = subckt_map.get(comp.subckt_name)
                if sub_def is None or not sub_def.components:
                    return (comp.subckt_name.lower() if case_insensitive
                            else comp.subckt_name)
            return None

        # Scan all subcircuit definitions
        for subckt in self.circuit.subcircuits:
            for comp in subckt.components:
                model = extract_model(comp)
                if model:
                    models.add(model)

        # Scan top-level components
        for comp in self.circuit.components:
            model = extract_model(comp)
            if model:
                models.add(model)

        return sorted(models)

    def get_subckts_using_model(self, model_name: str, case_insensitive: bool = True) -> List[str]:
        """
        Returns a list of subcircuit names that directly instantiate the given model.

        Args:
            model_name: The model name to search for.
            case_insensitive: If True (default), perform case-insensitive matching.
        """
        using_subckts = set()
        search_name = model_name.lower() if case_insensitive else model_name

        # Check in all subcircuit definitions
        for subckt in self.circuit.subcircuits:
            for comp in subckt.components:
                if hasattr(comp, 'model') and comp.model:
                    comp_model = comp.model.lower() if case_insensitive else comp.model
                    if comp_model == search_name:
                        using_subckts.add(subckt.name)
                        break  # Found usage in this subckt, move to next

        # Also check top level if not empty
        for comp in self.circuit.components:
            if hasattr(comp, 'model') and comp.model:
                comp_model = comp.model.lower() if case_insensitive else comp.model
                if comp_model == search_name:
                    using_subckts.add(self.circuit.name)
                    break

        return sorted(list(using_subckts))
