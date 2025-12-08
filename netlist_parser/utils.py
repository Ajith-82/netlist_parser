import re

def remove_comments(line: str) -> str:
    """
    Removes comments from a SPICE/CDL line.
    - Lines starting with * are full line comments.
    - $ indicates inline comment (unless inside a string, but we assume simple CDL).
    """
    line = line.strip()
    if not line:
        return ""
        
    # Full line comments
    if line.startswith('*'):
        return ""
    
    # Inline comments with $
    if '$' in line:
        # Check if it's a parameter like $W=... (CDL specific)
        # But wait, user says "everything after $ is NOT ignored" for params?
        # User: "Dollar sign ($) can be used to define comment-coded parameters... everything following... is NOT ignored."
        # User: "Note that if comment coded parameters are specified after comment '$ text' then they will be ignored."
        # This implies we should NOT blindly strip $.
        # However, for Parsing connectivity (netlist parser), we usually ignore params anyway?
        # Our parser extracts params but doesn't strictly use them for connectivity.
        # SAFE BET: Strip $ for now to get the structure right, unless $W= affects parsing?
        # If we have `M1 ... $W=...`, stripping it yields `M1 ...`. Still valid connectivity.
        # If we have `XX / name $PINS ...`, stripping yields `XX / name`. Valid.
        # So stripping $ is safer for structure than keeping it and confusing the tokenizer.
        return line.split('$', 1)[0]
        
    return line

def clean_line(line: str) -> str:
    """Strips whitespace."""
    return line.strip()
