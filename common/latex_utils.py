"""
LaTeX to Unicode & Telegram HTML Normalizer.

Transforms raw LaTeX formulas, Greek letters, math operators, superscripts,
subscripts, chemical formulas, and text wrappers into readable Unicode / Telegram HTML.
Preserves non-LaTeX text, paths, code identifiers (e.g. snake_case user_id), and BB-codes.
"""

from __future__ import annotations
import re

SUPERSCRIPT_MAP = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ', 'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ', 'i': 'ⁱ', 'j': 'ʲ',
    'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ', 'p': 'ᵖ', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ', 'u': 'ᵘ',
    'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 'y': 'ʸ', 'z': 'ᶻ',
    'A': 'ᴬ', 'B': 'ᴮ', 'D': 'ᴰ', 'E': 'ᴱ', 'G': 'ᴳ', 'H': 'ᴴ', 'I': 'ᴵ', 'J': 'ᴶ', 'K': 'ᴷ', 'L': 'ᴸ',
    'M': 'ᴹ', 'N': 'ᴺ', 'O': 'ᴼ', 'P': 'ᴾ', 'R': 'ᴿ', 'T': 'ᵀ', 'U': 'ᵁ', 'V': 'ⱽ', 'W': 'ᵂ',
    '°': '°', '‡': '‡', '†': '†', '*': '*'
}

SUBSCRIPT_MAP = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄', '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
    '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
    'a': 'ₐ', 'e': 'ₑ', 'h': 'ₕ', 'i': 'ᵢ', 'j': 'ⱼ', 'k': 'ₖ', 'l': 'ₗ', 'm': 'ₘ', 'n': 'ₙ',
    'o': 'ₒ', 'p': 'ₚ', 'r': 'ᵣ', 's': 'ₛ', 't': 'ₜ', 'u': 'ᵤ', 'v': 'ᵥ', 'x': 'ₓ'
}

GREEK_MAP = {
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'Gamma': 'Γ',
    'delta': 'δ', 'Delta': 'Δ',
    'epsilon': 'ε', 'varepsilon': 'ε',
    'zeta': 'ζ', 'eta': 'η',
    'theta': 'θ', 'vartheta': 'θ', 'Theta': 'Θ',
    'iota': 'ι', 'kappa': 'κ',
    'lambda': 'λ', 'Lambda': 'Λ',
    'mu': 'μ', 'nu': 'ν',
    'xi': 'ξ', 'Xi': 'Ξ',
    'pi': 'π', 'varpi': 'π', 'Pi': 'Π',
    'rho': 'ρ', 'varrho': 'ρ',
    'sigma': 'σ', 'varsigma': 'σ', 'Sigma': 'Σ',
    'tau': 'τ', 'upsilon': 'υ', 'Upsilon': 'Υ',
    'phi': 'φ', 'varphi': 'φ', 'Phi': 'Φ',
    'chi': 'χ', 'psi': 'ψ', 'Psi': 'Ψ',
    'omega': 'ω', 'Omega': 'Ω'
}

SYMBOL_MAP = {
    'times': '×',
    'cdot': '·',
    'div': '÷',
    'pm': '±',
    'mp': '∓',
    'approx': '≈',
    'sim': '~',
    'simeq': '≃',
    'cong': '≅',
    'equiv': '≡',
    'neq': '≠',
    'ne': '≠',
    'leq': '≤',
    'le': '≤',
    'geq': '≥',
    'ge': '≥',
    'll': '≪',
    'gg': '≫',
    'lt': '<',
    'gt': '>',
    'infty': '∞',
    'circ': '°',
    'degree': '°',
    'prime': '′',
    'dagger': '†',
    'ddagger': '‡',
    'to': '→',
    'rightarrow': '→',
    'leftarrow': '←',
    'Rightarrow': '⇒',
    'Leftarrow': '⇐',
    'implies': '⇒',
    'impliedby': '⇐',
    'iff': '⇔',
    'leftrightarrow': '↔',
    'Leftrightarrow': '⇔',
    'uparrow': '↑',
    'downarrow': '↓',
    'in': '∈',
    'notin': '∉',
    'subset': '⊂',
    'subseteq': '⊆',
    'cup': '∪',
    'cap': '∩',
    'forall': '∀',
    'exists': '∃',
    'nexists': '∄',
    'emptyset': '∅',
    'empty': '∅',
    'nabla': '∇',
    'partial': '∂',
    'sum': '∑',
    'prod': '∏',
    'int': '∫',
    'iint': '∬',
    'iiint': '∭',
    'oint': '∮',
    'dots': '…',
    'ldots': '…',
    'cdots': '…',
    'vdots': '⋮',
    'quad': '  ',
    'qquad': '    ',
}

MATH_OPERATORS = {
    'exp', 'ln', 'log', 'lg', 'sin', 'cos', 'tan', 'cot', 'tg', 'ctg',
    'sec', 'csc', 'arcsin', 'arccos', 'arctan', 'arctg', 'sinh', 'cosh',
    'tanh', 'coth', 'det', 'dim', 'gcd', 'hom', 'ker', 'inf', 'sup',
    'lim', 'liminf', 'limsup', 'max', 'min', 'arg', 'deg'
}


def to_superscript(s: str) -> str:
    """Converts string characters to Unicode superscripts where available."""
    return "".join(SUPERSCRIPT_MAP.get(c, c) for c in s)


def to_subscript(s: str) -> str:
    """Converts string characters to Unicode subscripts where available."""
    return "".join(SUBSCRIPT_MAP.get(c, c) for c in s)


def _unpack_braced_command(text: str, cmd: str) -> str:
    """Unpacks command with braces like \\text{...} handling nested braces."""
    pattern = re.compile(rf'\\{cmd}\s*\{{')
    while True:
        m = pattern.search(text)
        if not m:
            break
        start = m.start()
        content_start = m.end()
        depth = 1
        idx = content_start
        while idx < len(text) and depth > 0:
            if text[idx] == '{':
                depth += 1
            elif text[idx] == '}':
                depth -= 1
            idx += 1
        if depth == 0:
            inner = text[content_start:idx - 1]
            text = text[:start] + inner + text[idx:]
        else:
            break
    return text


def _replace_fmt_command(text: str, cmd: str, open_tag: str, close_tag: str) -> str:
    """Replaces formatting command like \\textbf{...} with HTML tags."""
    pattern = re.compile(rf'\\{cmd}\s*\{{')
    while True:
        m = pattern.search(text)
        if not m:
            break
        start = m.start()
        content_start = m.end()
        depth = 1
        idx = content_start
        while idx < len(text) and depth > 0:
            if text[idx] == '{':
                depth += 1
            elif text[idx] == '}':
                depth -= 1
            idx += 1
        if depth == 0:
            inner = text[content_start:idx - 1]
            text = text[:start] + f"{open_tag}{inner}{close_tag}" + text[idx:]
        else:
            break
    return text


def normalize_latex(text: str) -> str:
    """
    Transforms LaTeX formatting into clean Unicode and Telegram-supported HTML.
    Safe against non-LaTeX text, file paths, and code identifiers.
    """
    if not text or not isinstance(text, str):
        return "" if text is None else str(text)

    # Fast check: skip if neither backslash, math delimiter, exponent, nor subscript is present
    if '\\' not in text and '$' not in text and '^' not in text and '_' not in text:
        return text

    # 1. Strip math mode delimiters ($$, \[, \], \(\)) while protecting escaped dollars (\$)
    text = re.sub(r'(?<!\\)\$\$(.*?)(?<!\\)\$\$', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.*?)\\\)', r'\1', text, flags=re.DOTALL)
    # Inline $...$ is only stripped if it contains math syntax (formulas, operators, commands, carets, subscripts)
    def _strip_inline_dollar(m: re.Match) -> str:
        inner = m.group(1)
        if any(c in inner for c in ('\\', '^', '_', '=', '±', '≠', '≤', '≥', '≈', '×', '·', '<', '>')):
            return inner
        return m.group(0)
    text = re.sub(r'(?<!\\)\$(?!\s)([^$\n]+?)(?<!\s)(?<!\\)\$', _strip_inline_dollar, text)

    # 2. Escaped characters: \\%, \\_, \\&, \\$, \\#, \\{, \\}
    text = re.sub(r'\\([%$&_#{}\\])', r'\g<1>', text)

    # 3. Standard math operator functions: \\exp, \\ln, \\sin, etc.
    for op in MATH_OPERATORS:
        text = re.sub(rf'\\{op}(?![a-zA-Z])', op, text)

    # 4. Text wrappers: \\text{...}, \\mathrm{...}, \\operatorname{...}, \\mbox{...}
    for cmd in ['text', 'mathrm', 'operatorname', 'mbox', 'textnormal']:
        text = _unpack_braced_command(text, cmd)

    # 5. Bold and Italic: \\textbf, \\mathbf, \\textit, \\mathit
    text = _replace_fmt_command(text, 'textbf', '<b>', '</b>')
    text = _replace_fmt_command(text, 'mathbf', '<b>', '</b>')
    text = _replace_fmt_command(text, 'textit', '<i>', '</i>')
    text = _replace_fmt_command(text, 'mathit', '<i>', '</i>')

    # 6. \\sqrt{...} -> √(inner)
    pattern_sqrt = re.compile(r'\\sqrt\s*\{')
    while True:
        m = pattern_sqrt.search(text)
        if not m:
            break
        start = m.start()
        content_start = m.end()
        depth = 1
        idx = content_start
        while idx < len(text) and depth > 0:
            if text[idx] == '{':
                depth += 1
            elif text[idx] == '}':
                depth -= 1
            idx += 1
        if depth == 0:
            inner = text[content_start:idx - 1]
            text = text[:start] + f"√({inner})" + text[idx:]
        else:
            break

    # 7. \\frac{num}{den} -> (num)/(den)
    pattern_frac = re.compile(r'\\frac\s*\{')
    while True:
        m = pattern_frac.search(text)
        if not m:
            break
        start = m.start()
        idx1 = m.end()
        depth = 1
        while idx1 < len(text) and depth > 0:
            if text[idx1] == '{':
                depth += 1
            elif text[idx1] == '}':
                depth -= 1
            idx1 += 1
        if depth != 0:
            break
        num = text[m.end():idx1 - 1]
        while idx1 < len(text) and text[idx1].isspace():
            idx1 += 1
        if idx1 < len(text) and text[idx1] == '{':
            idx2 = idx1 + 1
            depth = 1
            while idx2 < len(text) and depth > 0:
                if text[idx2] == '{':
                    depth += 1
                elif text[idx2] == '}':
                    depth -= 1
                idx2 += 1
            if depth == 0:
                den = text[idx1 + 1:idx2 - 1]
                text = text[:start] + f"({num})/({den})" + text[idx2:]
                continue
        break

    # 8. Commands within superscripts/subscripts like ^\\circ, ^\\dagger, ^\\ddagger
    text = re.sub(r'\^\\circ\b', '^°', text)
    text = re.sub(r'\^\\dagger\b', '^†', text)
    text = re.sub(r'\^\\ddagger\b', '^‡', text)
    text = re.sub(r'\^\\prime\b', '^′', text)
    text = re.sub(r'_\\circ\b', '_°', text)

    # 9. Greek letters and math symbols (protecting Windows paths like C:\to\ or dir\in\file)
    for name, sym in {**GREEK_MAP, **SYMBOL_MAP}.items():
        text = re.sub(rf'(?<![a-zA-Z]:)(?<![\\/])\\{name}(?![a-zA-Z0-9_\\/])\s*', sym + ' ', text)

    # Attach prefix operators (Δ, δ, ∂, ∇) to single variable letter: Δ G -> ΔG, ∂ x -> ∂x
    text = re.sub(r'([Δδ∂∇])\s+([A-Za-z])(?![a-zA-Z0-9])', r'\1\2', text)

    # Fix space after symbol if it precedes punctuation or another symbol
    text = re.sub(r'([α-ωΑ-Ω×·÷±∓≈~≃≅≡≠≤≥≪≫<>∞°′†‡→←⇒⇐↔⇔↑↓∈∉⊂⊆∪∩∀∃∄∅∇∂∑∏∫∬∭∮…])\s+([,.:;!?)\]}\^_\-])', r'\1\2', text)
    # Fix space before symbol if after opening bracket
    text = re.sub(r'([(⟦\[{])\s+([α-ωΑ-Ω×·÷±∓≈~≃≅≡≠≤≥≪≫<>∞°′†‡→←⇒⇐↔⇔↑↓∈∉⊂⊆∪∩∀∃∄∅∇∂∑∏∫∬∭∮…])', r'\1\2', text)

    # 10. Superscripts:
    # 10a. Explicit braces: ^{11}, ^{-(x+y)}, ^{2}
    text = re.sub(r'\^\{([^}]+)\}', lambda m: to_superscript(m.group(1)), text)

    # 10b. Single char or number: ^2, ^10, ^+
    text = re.sub(r'\^([0-9]+|[a-zA-Z+-=()°‡†*])', lambda m: to_superscript(m.group(1)), text)

    # 11. Subscripts:
    # 11a. Explicit braces: _{12}, _{max}, _{p}
    text = re.sub(r'_\{([^}]+)\}', lambda m: to_subscript(m.group(1)), text)

    # 11b. Digits after chemical elements/variables: CO_2, H_2O, x_1, (Fe)_2 (protecting user_123, post_569139)
    pattern_sub = re.compile(r'(?:(?<=[A-Z])|(?<=[A-Z][a-z])|(?<=\b[a-z])|(?<=[)\]}α-ωΑ-Ω]))_([0-9]+)')
    text = pattern_sub.sub(lambda m: to_subscript(m.group(1)), text)

    # 11c. Single letter variable index: f_p, n_e, f_l, E_a (preceded by single letter, followed by word boundary)
    text = re.sub(r'(?<=\b[A-Za-zα-ωΑ-Ω])_([a-zA-Z])(?![a-zA-Z0-9])', lambda m: to_subscript(m.group(1)), text)

    # 12. Clean double spaces
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()
