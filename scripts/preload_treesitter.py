import tree_sitter_language_pack as t

languages = [
    "python",
    "go",
    "java",
    "javascript",
    "typescript",
    "c",
    "cpp",
    "c_sharp",
    "rust",
    "ruby",
    "kotlin",
    "php",
    "scala",
    "bash",
    "html",
    "css",
    "sql",
    "toml",
    "yaml",
    "json",
    "xml",
]

for lang in languages:
    try:
        t.get_language(lang)
        print(f" Loaded: {lang}")
    except Exception as e:
        print(f" Failed: {lang} -> {e}")