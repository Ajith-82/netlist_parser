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
        
    # Full line comments. The CDL control line '*.GLOBAL' is significant:
    # hand it to the parser as '.GLOBAL'.
    if line.startswith('*'):
        if line[:8].upper() == '*.GLOBAL' and (len(line) == 8 or line[8].isspace()):
            line = line[1:]
        else:
            return ""
    
    # Inline comments with $:
    # A bare '$' (followed by whitespace or end of line) starts a comment.
    # CDL comment-coded parameters like '$SUB=VSS', '$[model]', '$W=1u' are
    # significant and must be preserved for the parser to interpret.
    if '$' in line:
        m = re.search(r'\$(?=\s|$)', line)
        if m:
            return line[:m.start()].rstrip()

    return line

def clean_line(line: str) -> str:
    """Strips whitespace."""
    return line.strip()

def tokenize_line(line: str) -> list[str]:
    """
    Splits a line into tokens, respecting single quotes for HSPICE-style expressions.
    Example: "w='1u + 2u'" -> ["w='1u + 2u'"] instead of ["w='1u", "+", "2u'"]
    """
    # Regex captures:
    # 1. Sequences starting with non-space/non-quote, optionally containing quoted sections.
    #    This handles: word, key=val, key='v a l'
    # 2. Standalone quoted strings: 'v a l'
    # 'w = 1u' and 'w= 1u' are the same as 'w=1u'
    if '=' in line:
        line = re.sub(r"\s*=\s*", "=", line)
    pattern = r"[^\s']+(?:'[^']*'[^\s']*)*|'[^']*'"
    return re.findall(pattern, line)
