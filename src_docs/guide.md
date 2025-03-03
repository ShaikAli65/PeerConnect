# Documentation Guide

## Header

- First line is a level one header naming the module or package

```md
# Awesome Module/Package
```

- Second line should have fully qualified module name or package name, with it's hyperlink pointing to source file
*Note*: this can be optional if doc does not have source file

```md
[src.awesome](#link-to-src)
```

- Third line contains a *little* description about doc file itself

## Content

- Documenting a `class` or `function` it's name should be a level 2 or 3 header naming the class
- Following the class header, a code snippet having `class` or `function` signature should be provided
- Later the `function` or `class` can be documented descriptively

**Example**:

### Awesome Class

```py
class AwesomeClass(AwesomeBase, AwesomeMixIn):...
```

- class detail
- full documentation
- methods docs follow same signature as a [function](#awesome-function), typically with a high level of header relative to class header level
- optional status of class [WIP,RIP,...](/src_docs/README.md#legend)

### Awesome Function

```py
def awesome_function(arg1, arg2: type, **kwargs):...
```

- function detail
- function documentation
- optional status of function [WIP,RIP,...](/src_docs/README.md#legend)

Consider this when writing docs:

```txt
The class docstring should not repeat unnecessary information, such as that the class is a class.
```

This applies to `function` or `module` or `package`
[reference](<https://google.github.io/styleguide/pyguide.html#:~:text=All%20class%20docstrings,is%20a%20class.>)

## Footer

- Should contain a break line
- a link naming `back` pointing outward into documentation heirarchy

```md
---

[back](/src_docs)
```
