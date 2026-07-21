# Overview

This is a hand-written guide page, written in Markdown via
[MyST](https://myst-parser.readthedocs.io/), living alongside the
autodoc-generated API reference. Use pages like this one for narrative
content — architecture explanations, tutorials, setup instructions — that
doesn't belong in a docstring.

To add another page:

1. Create a new `.md` file under `docs/guides/`.
2. Add its filename (without the extension) to the `toctree` in
   [index.rst](../index.rst).

## Linking to other pages

Regular Markdown links work for other pages in the docs:

- [API Reference](../api.rst)

## Linking to autodoc objects

MyST also supports Sphinx's cross-reference roles, so you can link straight
to a class or function documented via autodoc, e.g. the node poller:

{py:class}`koi_net.components.poller.NodePoller`

## Code blocks

```python
from koi_net.components.poller import NodePoller

poller = NodePoller(...)
```

## Admonitions

```{note}
Admonitions like this one are built into MyST — no extra Sphinx extension
needed beyond `myst_parser` itself.
```
