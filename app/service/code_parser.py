from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter
from tree_sitter import Language, Parser
import tree_sitter_language_pack as tslp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

import os


def _load_language(name: str) -> Optional[Language]:
    try:
        pack_name = _PACK_NAME_MAP.get(name, name)
        return tslp.get_language(pack_name)
    except Exception as e:
        logger.warning(f"[CodeParser] Grammar '{name}' unavailable: {e}")
        return None



_PACK_NAME_MAP: dict[str, str] = {
    "c_sharp": "csharp",   
}

_language_cache: dict[str, Optional[Language]] = {}

def get_language(name: str) -> Optional[Language]:
    if name not in _language_cache:
        _language_cache[name] = _load_language(name)
    return _language_cache[name]


_LANG_HINTS: dict[str, str] = {
    "c":          "C language, systems programming, pointers, structs, memory management",
    "cpp":        "C++ language, classes, templates, STL, memory management, RAII",
    "javascript": "JavaScript language, functions, callbacks, promises, async await, ES6 modules",
    "typescript": "TypeScript language, static types, interfaces, generics, decorators, enums",
    "rust":       "Rust language, ownership, lifetimes, traits, borrowing, enums, pattern matching",
    "go":         "Go language, goroutines, channels, interfaces, structs, defer, error handling",
    "scala":      "Scala language, functional programming, case classes, traits, pattern matching",
    "kotlin":     "Kotlin language, coroutines, data classes, extension functions, null safety",
    "php":        "PHP language, web development, classes, namespaces, traits, Laravel",
    "ruby":       "Ruby language, blocks, mixins, modules, metaprogramming, Rails",
    "swift":      "Swift language, optionals, protocols, generics, closures, value types",
    "apex":       "Apex language, Salesforce, SOQL, triggers, classes, DML operations",
}


LANGUAGE_NODE_TYPES: dict[str, list[str]] = {
    "python":     [
        "class_definition",
        "function_definition",
        "decorated_definition",
    ],
    "go":         [
        "function_declaration",
        "method_declaration",
        "type_declaration",
    ],
    "java":       [
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "method_declaration",
        "constructor_declaration",
        "annotation_type_declaration",
    ],
    "javascript": [
        "function_declaration",
        "class_declaration",
        "method_definition",
        "export_statement",
    ],
    "typescript": [
        "function_declaration",
        "class_declaration",
        "method_definition",
        "interface_declaration",        
        "type_alias_declaration",       
        "enum_declaration",             
        "abstract_class_declaration",   
        "export_statement",
    ],
    "c":          [
        "function_definition",
        "struct_specifier",
        "enum_specifier",
    ],
    "cpp":        [
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "namespace_definition",
        "template_declaration",
    ],
    "c_sharp":    [
        "class_declaration",
        "interface_declaration",
        "method_declaration",
        "constructor_declaration",
        "namespace_declaration",
        "enum_declaration",
    ],
    "rust":       [
        "function_item",
        "impl_item",
        "struct_item",
        "enum_item",
        "trait_item",
        "mod_item",
    ],
    "ruby":       [
        "class",
        "module",
        "method",
        "singleton_method",
    ],
    "kotlin":     [
        "class_declaration",
        "function_declaration",
        "object_declaration",
        "companion_object",
        "property_declaration",    
        "interface_declaration",
    ],
    "php":        [
        "function_definition",
        "class_declaration",
        "method_declaration",
        "interface_declaration",
    ],
    "scala":      [
        "class_definition",
        "object_definition",
        "trait_definition",
        "function_definition",
        "val_definition",           
        "var_definition",           
    ],
    "bash":       [
        "function_definition",
    ],
    "html":       [
        "script_element",
        "style_element",
    ],
    "css":        [
        "rule_set",
        "at_rule",
        "media_statement",
    ],
    "sql":        [
        "create_table_statement",
        "create_function_statement",
        "create_view_statement",        
        "create_index_statement",       
        "create_trigger_statement",     
        "alter_table_statement",        
        "select_statement",
        "insert_statement",
        "update_statement",
        "delete_statement",
    ],
    "toml":       [
        "table",
        "array_table",
    ],
    "yaml":       [
        "block_mapping",
        "block_sequence",
    ],
    "json":       [
        "object",
    ],
    "xml":        [
        "element",
        "document",
    ],
}


EXT_TO_LANG: dict[str, str] = {
    ".py":        "python",
    ".go":        "go",
    ".java":      "java",
    ".js":        "javascript",
    ".jsx":       "javascript",
    ".ts":        "typescript",
    ".tsx":       "typescript",
    ".c":         "c",
    ".h":         "c",
    ".cpp":       "cpp",
    ".hpp":       "cpp",
    ".cs":        "c_sharp",
    ".rs":        "rust",
    ".rb":        "ruby",
    ".kt":        "kotlin",
    ".php":       "php",
    ".scala":     "scala",
    ".sh":        "bash",
    ".html":      "html",
    ".css":       "css",
    ".scss":      "css",
    ".sql":       "sql",
    ".toml":      "toml",
    ".yaml":      "yaml",
    ".yml":       "yaml",
    ".json":      "json",
    ".xml":       "xml",            
    # Salesforce / Apex — regex fallback
    ".cls":       "apex",
    ".trigger":   "apex",
    ".apex":      "apex",
    ".page":      "apex",
    ".component": "apex",
    # Swift — regex fallback
    ".swift":     "swift",
    # Documents — plain text splitting
    ".md":        "markdown",
    ".txt":       "text",
    ".pdf":       "pdf",
    ".docx":      "docx",
    ".doc":       "docx",
}



OVERLAP_CHARS = int(os.getenv("OVERLAP_CHARS",  "50"))
FALLBACK_CHUNK_SIZE = int(os.getenv("FALLBACK_CHUNK_SIZE",  "1000"))
FALLBACK_OVERLAP = int(os.getenv("FALLBACK_OVERLAP",  "100"))

MAX_CHUNK_CHARS  = int(os.getenv("MAX_CHUNK_CHARS",  "2500"))
SOFT_CHUNK_CHARS = int(os.getenv("SOFT_CHUNK_CHARS", "1500"))
_PREAMBLE_CHARS  = int(os.getenv("PREAMBLE_CHARS",   "200"))

_sub_splitter = RecursiveCharacterTextSplitter(
    chunk_size=SOFT_CHUNK_CHARS,
    chunk_overlap=OVERLAP_CHARS,
)


@dataclass
class CodeChunk:
    content: str            # context header + code (sent to LLM / embedded)
    raw_content: str        # code only (for debug / audit)
    symbol: Optional[str]   # extracted function / class name
    language: str
    chunk_index: int
    file_name: str
    file_path: str
    workspace_path: str
    start_line: int = 0
    end_line: int = 0


def _make_header(file_path: str, workspace_path: str, language: str,
                 symbol: Optional[str]) -> str:
    try:
        rel = os.path.relpath(file_path, workspace_path)
    except ValueError:
        rel = file_path  # Windows cross-drive edge case
    symbol_part = f"\n# Symbol: {symbol}" if symbol else ""
    hint = _LANG_HINTS.get(language, "")
    hint_part = f"\n# Context: {hint}" if hint else ""
    return (
        f"# Language: {language}{hint_part}\n"
        f"# File: {rel}\n"
        f"# Workspace: {workspace_path}"
        f"{symbol_part}\n"
        f"---\n"
    )


def _extract_symbol_name(node, source: bytes) -> Optional[str]:
    for child in node.children:
        if child.type in ("identifier", "name", "type_identifier",
                          "property_identifier", "field_identifier"):
            return source[child.start_byte:child.end_byte].decode(errors="replace")
    return None


def _with_overlap(chunks: list[str], overlap: int) -> list[str]:
    if len(chunks) <= 1:
        return chunks
    result = [chunks[0]]
    for i in range(1, len(chunks)):
        tail = chunks[i - 1][-overlap:]
        result.append(tail + chunks[i])
    return result



_APEX_PATTERN = re.compile(
    r"""
    (?:
        (?:public|private|protected|global|static|override|virtual|abstract
           |with\s+sharing|without\s+sharing)\s+
    )*
    (?:
        class\s+\w+|
        interface\s+\w+|
        trigger\s+\w+\s+on\s+\w+\s*\(
            (?:before\s+insert|before\s+update|before\s+delete|
               after\s+insert|after\s+update|after\s+delete|after\s+undelete)
            (?:\s*,\s*
            (?:before\s+insert|before\s+update|before\s+delete|
               after\s+insert|after\s+update|after\s+delete|after\s+undelete)
            )*\s*\)|
        (?:void|Integer|String|Boolean|Double|Long|Decimal|Id|
           List|Map|Set|Object|\w+)\s+\w+\s*\(
    )
    """,
    re.VERBOSE | re.MULTILINE,
)

_SWIFT_PATTERN = re.compile(
    r"""
    (?:(?:public|private|internal|open|fileprivate|static|class
         |override|final|mutating)\s+)*
    (?:func\s+\w+|class\s+\w+|struct\s+\w+|enum\s+\w+
       |protocol\s+\w+|extension\s+\w+|init\b)
    """,
    re.VERBOSE | re.MULTILINE,
)


def _regex_split(source: str, lang: str) -> list[Tuple[str, Optional[str]]]:
    pattern = _APEX_PATTERN if lang == "apex" else _SWIFT_PATTERN
    matches = list(pattern.finditer(source))
    if not matches:
        return [(source, None)]
    boundaries = [m.start() for m in matches] + [len(source)]
    chunks = []
    for i in range(len(matches)):
        text = source[boundaries[i]:boundaries[i + 1]].strip()
        if text:
            symbol = matches[i].group(0).strip().split("\n")[0][:80]
            chunks.append((text, symbol))
    return chunks if chunks else [(source, None)]



def _treesitter_chunks(
    source_bytes: bytes,
    lang_name: str,
    language: Language,
) -> list[tuple[str, Optional[str], int, int]]:
    """
    Recursively walks the AST, always preferring leaf-level extraction.
    A node is only emitted when:
      - it has no target-type children (true leaf in our semantic tree), OR
      - it fits within MAX_CHUNK_CHARS AND has no further splittable children
    If even a leaf exceeds MAX_CHUNK_CHARS, it is character-split as last resort.
    """
    parser = Parser(language)
    tree   = parser.parse(source_bytes)
    target_types = set(LANGUAGE_NODE_TYPES.get(lang_name, []))

    results: list[tuple[str, Optional[str], int, int]]  = []
    collected_ranges: list[tuple[int, int]]              = []

    def _build_preamble(node) -> str:
        """
        First _PREAMBLE_CHARS of a node — used as context header when
        a child chunk needs to know which class/function it belongs to.
        """
        raw = source_bytes[node.start_byte:node.end_byte].decode(errors="replace")
        return raw[:_PREAMBLE_CHARS].rstrip() + "\n# ...\n"

    def _emit_leaf(
        text: str,
        symbol: Optional[str],
        sl: int,
        el: int,
        preamble: str,
    ) -> None:
        """
        Terminal emitter. Prepends preamble, then enforces MAX_CHUNK_CHARS
        via character splitting if needed.
        """
        full_text = (preamble + text) if preamble else text

        if len(full_text) <= MAX_CHUNK_CHARS:
            results.append((full_text, symbol, sl, el))
            return

        sub_chunks = _sub_splitter.split_text(full_text)
        for i, sub in enumerate(sub_chunks):
            # Re-attach preamble on every continuation so each sub-chunk
            # carries context even when retrieved in isolation
            if i > 0 and preamble:
                sub = preamble + sub
            results.append((sub, symbol, sl, el))

    def _walk(node, preamble: str = "") -> None:
        """
        Recursively walk target-type nodes.

        Decision tree at each node:
          1. Not a target type?        → walk children, pass preamble down
          2. Target type, has target-type children?
               → always recurse deeper; emit a "skeleton" of this node
                 (signature + gaps between children) so context is preserved
          3. Target type, no target-type children (semantic leaf)?
               → emit via _emit_leaf (handles oversized via char-split)
        """
        if node.type not in target_types:
            for child in node.children:
                _walk(child, preamble)
            return


        text   = source_bytes[node.start_byte:node.end_byte].decode(errors="replace")
        symbol = _extract_symbol_name(node, source_bytes)
        sl, el = node.start_point[0], node.end_point[0]
        collected_ranges.append((node.start_byte, node.end_byte))

        # Find direct children that are themselves target types
        target_children = [c for c in node.children if c.type in target_types]

        if not target_children:
            _emit_leaf(text, symbol, sl, el, preamble)
            return

        # ── CASE 2: has semantic children — recurse deeper ────────────────
        # Build this node's preamble for its children
        node_preamble = _build_preamble(node)

        # Emit the "skeleton": signature + non-child content (fields,
        # decorators, class-level constants — anything between methods)
        skeleton = _extract_skeleton(node, source_bytes, target_children)
        if skeleton.strip() and len(skeleton.strip()) > 20:
            _emit_leaf(skeleton, symbol, sl, el, preamble)

        # Recurse into every target-type child with this node's preamble
        for child in target_children:
            _walk(child, preamble=node_preamble)

    _walk(tree.root_node)

    # ── module-level leftover (imports, globals, top-level constants) ─────────
    if collected_ranges:
        collected_ranges.sort(key=lambda r: r[0])
        leftover_parts: list[bytes] = []
        prev_end = 0
        for start, end in collected_ranges:
            if start > prev_end:
                leftover_parts.append(source_bytes[prev_end:start])
            prev_end = max(prev_end, end)
        if prev_end < len(source_bytes):
            leftover_parts.append(source_bytes[prev_end:])

        leftover_text = b"".join(leftover_parts).decode(errors="replace").strip()
        if leftover_text and len(leftover_text) > 20:
            tagged = f"# {lang_name} module-level code\n{leftover_text}"
            # module-level code emitted first — provides import/global context
            # for all subsequent chunks
            module_chunks: list[tuple[str, Optional[str], int, int]] = []
            _emit_leaf_standalone(tagged, "module-level", 0, 0, "", module_chunks)
            results[0:0] = module_chunks   # prepend

    return results


def _extract_skeleton(
    node,
    source_bytes: bytes,
    target_children: list,
) -> str:
    """
    Returns the text of node with the byte ranges of its target-type
    children removed — i.e. the class/struct skeleton: its signature,
    field declarations, class-level constants, decorators.

    Example for a Python class:
        class Foo(Bar):
            CONSTANT = 42          # kept   (not a function/class)
            def method(self): ...  # removed (extracted separately)
    """
    child_ranges = sorted((c.start_byte, c.end_byte) for c in target_children)
    parts: list[bytes] = []
    prev = node.start_byte
    for start, end in child_ranges:
        if start > prev:
            parts.append(source_bytes[prev:start])
        prev = max(prev, end)
    if prev < node.end_byte:
        parts.append(source_bytes[prev:node.end_byte])
    return b"".join(parts).decode(errors="replace")

def _emit_leaf_standalone(
    text: str,
    symbol: Optional[str],
    sl: int,
    el: int,
    preamble: str,
    out: list,
) -> None:
    """Same logic as _emit_leaf but writes to an external list."""
    full_text = (preamble + text) if preamble else text
    if len(full_text) <= MAX_CHUNK_CHARS:
        out.append((full_text, symbol, sl, el))
        return
    sub_chunks = _sub_splitter.split_text(full_text)
    for i, sub in enumerate(sub_chunks):
        if i > 0 and preamble:
            sub = preamble + sub
        out.append((sub, symbol, sl, el))

class CodeParser:

    _fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=FALLBACK_CHUNK_SIZE,
        chunk_overlap=FALLBACK_OVERLAP,
    )

    def parse_file(
        self,
        file_content: bytes,
        file_name: str,
        file_extension: str,
        file_path: str,
        workspace_path: str,
    ) -> List[CodeChunk]:
        ext = file_extension.lower()
        lang = EXT_TO_LANG.get(ext, "text")

        if lang in ("markdown", "text", "pdf", "docx"):
            return self._text_chunks(file_content, file_name, file_extension,
                                     file_path, workspace_path, lang)

        if lang in ("apex", "swift"):
            return self._regex_chunks(file_content, file_name, file_extension,
                                      file_path, workspace_path, lang)

        language = get_language(lang)
        if language is None:
            return self._fallback_chunks(file_content, file_name, file_extension,
                                         file_path, workspace_path, lang)
        try:
            return self._treesitter_parse(file_content, file_name, file_extension,
                                          file_path, workspace_path, lang, language)
        except Exception as e:
            logger.warning(
                f"[CodeParser] tree-sitter failed for {file_name} ({lang}): {repr(e)}"
                " → falling back to RecursiveCharacterTextSplitter"
            )
            return self._fallback_chunks(file_content, file_name, file_extension,
                                         file_path, workspace_path, lang)

    def _build_chunks(
        self,
        raw_chunks: Sequence[Tuple[str, Optional[str]]],
        file_name: str,
        file_extension: str,
        file_path: str,
        workspace_path: str,
        lang: str,
    ) -> List[CodeChunk]:
        if not raw_chunks:
            return []
        texts = [r[0] for r in raw_chunks]
        texts_with_overlap = _with_overlap(texts, OVERLAP_CHARS)
        chunks = []
        for idx, ((raw, symbol), with_ov) in enumerate(zip(raw_chunks, texts_with_overlap)):
            header = _make_header(file_path, workspace_path, lang, symbol)
            chunks.append(CodeChunk(
                content=header + with_ov,
                raw_content=raw,
                symbol=symbol,
                language=lang,
                chunk_index=idx,
                file_name=file_name,
                file_path=file_path,
                workspace_path=workspace_path,
            ))
        return chunks

    def _treesitter_parse(
        self, file_content: bytes, file_name: str, file_extension: str,
        file_path: str, workspace_path: str, lang: str, language: Language,
    ) -> List[CodeChunk]:
        raw_results = _treesitter_chunks(file_content, lang, language)
        if not raw_results:
            return self._fallback_chunks(file_content, file_name, file_extension,
                                         file_path, workspace_path, lang)
        raw_chunks: list[Tuple[str, Optional[str]]] = [
            (text, symbol) for text, symbol, _, _ in raw_results
        ]
        return self._build_chunks(raw_chunks, file_name, file_extension,
                                  file_path, workspace_path, lang)

    def _regex_chunks(
        self, file_content: bytes, file_name: str, file_extension: str,
        file_path: str, workspace_path: str, lang: str,
    ) -> List[CodeChunk]:
        source = file_content.decode(errors="replace")
        raw_chunks: list[Tuple[str, Optional[str]]] = _regex_split(source, lang)
        return self._build_chunks(raw_chunks, file_name, file_extension,
                                  file_path, workspace_path, lang)

    def _fallback_chunks(
        self, file_content: bytes, file_name: str, file_extension: str,
        file_path: str, workspace_path: str, lang: str,
    ) -> List[CodeChunk]:
        source = file_content.decode(errors="replace")
        splits = self._fallback_splitter.split_text(source)
        raw_chunks: list[Tuple[str, Optional[str]]] = [
            (s, None) for s in splits if s.strip()
        ]
        return self._build_chunks(raw_chunks, file_name, file_extension,
                                  file_path, workspace_path, lang)

    def _text_chunks(
        self, file_content: bytes, file_name: str, file_extension: str,
        file_path: str, workspace_path: str, lang: str,
    ) -> List[CodeChunk]:
        source = file_content.decode(errors="replace")
        splits = self._fallback_splitter.split_text(source)
        raw_chunks: list[Tuple[str, Optional[str]]] = [
            (s, None) for s in splits if s.strip()
        ]
        return self._build_chunks(raw_chunks, file_name, file_extension,
                                  file_path, workspace_path, lang)


code_parser = CodeParser()