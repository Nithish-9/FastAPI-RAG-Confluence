---
title: "Heavyweight Markdown AST Stress Test"
version: "2026.1.0"
tags: [tree-sitter, parsing, gfm, markdown]
nested:
  property: true
---

# Heading Level 1 (Document Root)

This is a paragraph containing basic formatting elements like **strong importance via asterisks**, __strong importance via underscores__, *regular emphasis*, and _alternative emphasis_. You can also use ~~strikethrough text~~ for corrected data tracks.

## Heading Level 2 (Structural Elements)

> This is a single-line blockquote block element.
> 
> > This is a nested second-tier blockquote sequence.
> > It tracks multiple lines of structural citation payload.

### Heading Level 3 (Lists and Task Matrix Configuration)

1. First ordered structural list item
2. Second ordered list item containing a nested framework:
   - Unordered sub-item tracking variant A
   - Unordered sub-item tracking variant B
3. Third ordered item with an embedded `inline_code_node` variable reference.

#### Heading Level 4 (GitHub Flavored Markdown Extensions)

- [x] Completed index structural mapping target
- [ ] Incomplete parser boundary validation test
- [x] ~~Completed but struck out operational task item~~

---

## Code Blocks & Syntax Containment Contexts

Below is a fenced code block specifying an explicit syntax language tag (`javascript`). A robust tree-sitter indexer must handle this via a language injection layout:

```javascript
// Internal language injection block
function parseTreeSitterNode(node) {
    const type = node?.type ?? "UNKNOWN_LEAF";
    return `AST_Token:[${type}]`;
}