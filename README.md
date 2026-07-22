# KOI-net

[![PyPI](https://img.shields.io/pypi/v/koi-net)](https://pypi.org/project/koi-net/)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://dynamicalsystemsgroup.github.io/koi-net/index.html)

*This protocol and framework are the result of several iterations of KOI research, [read more here](https://github.com/DynamicalSystemsGroup/koi).*

KOI-net (Knowledge Organization Infrastructure Network) can be understood as both a network protocol for distributed knowledge processing, and as a Python framework for building nodes, networks, and applications on top of that protocol. This repo is the implementation of that framework.

For information about the KOI-net protocol, see the [official specification](https://dynamicalsystemsgroup.github.io/koi-net-spec). 
# Quick Start
## Installation

(Optionally) create and activate a virtual environment, and install KOI-net:

```shell
$ pip install koi-net
```

## Create a Simple Partial Node

The KOI-net framework is built around the [dependency injection](https://en.wikipedia.org/wiki/Dependency_injection) pattern. Node classes are *containers* for interdependent *components* implementing internal subsystems. Each node inherits from a base partial or full node class, which comes with ~36 default components. At a minimum, each node needs to implement a config component:

```python
from koi_net.config import PartialNodeConfig, KoiNetConfig, PartialNodeProfile  

class MyPartialNodeConfig(PartialNodeConfig):
	koi_net: KoiNetConfig = KoiNetConfig(
		node_name="partial",
		node_profile=PartialNodeProfile()
	)
```

Which is set in the node container:

```python
from koi_net.core import PartialNode

class MyPartialNode(PartialNode):
	config_schema = MyPartialNodeConfig
```

Finally, the main method can be set to build and run the node:

```python
if __name__ == "__main__":
	MyPartialNode().run()
```

See `examples/coordinator.py` for a more complex example node, or see [the docs](https://dynamicalsystemsgroup.github.io/koi-net) for more information on the KOI-net framework.

This framework depends on [rid-lib](https://github.com/DynamicalSystemsGroup/rid-lib), the Python implementation of the RID protocol.

# Documentation

This project uses Sphinx to generate documentation from docstrings. The `docs.yml` GitHub workflow automatically build and deploys the docs to GitHub Pages. To build the docs locally, run the following command:
```shell
$ uv run --extra docs sphinx-build -b html docs docs/_build/html
```