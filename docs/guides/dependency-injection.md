# Dependency Injection

As the complexity of a KOI node has grown over time, the need for a system to manage the network of components and dependency between them emerged. While existing dependency injection frameworks for Python exist, the ones I tried were overly verbose or bulky and required significant overhead to learn how to use them. My goal for this system was to create a simple, lightweight alternative that is easy to use, and pulling out complexity into reusable infrastructure.

In complex systems, you inevitably develop many interconnected components that depend on each other. Changes to dependencies of one component, or swapping in a new one with the same shape requires tedious refactoring in several locations. Furthermore, it becomes hard to keep track of this web of components and circular dependency loops may emerge, preventing the system from initializing.

Dependency injection attempts to solve this problem. It is a declarative pattern in which each component names their dependencies, which are injected during initialization. Components live within a container, which is responsible for wiring them together.

## Architecture Summary
The DI system defines three primary types of objects: components, assemblies, and containers. An assembly is a "blueprint" for a system, declaring which components it is made up of. Components are the building blocks, defining smaller, sometimes modular subsystems. A component can be of one of two types: a singleton, which is a class (or any callable) which declares its dependencies in its init method and is instantiated as a single object, or an object which is a constant (of any Python type) which is just treated "as is." When an assembly is instantiated, it resolves all dependencies, initializes singletons, and returns a container containing all of the components defined in the assembly. The container creates a lifecycle object, and exposes lifecycle methods to start, stop, and check the state of the container.

A dummy example shows the distinction between each type of DI object:
```python
from pathlib import Path
from koi_net.base import BaseAssembly

class ComponentA:
    pass

class ComponentB:
    def __init__(self, comp_a: ComponentA):
        self.comp_a = comp_a
    
class MyAssembly(BaseAssembly):
    comp_a = ComponentA
    comp_b = ComponentB
    
container = MyAssembly(root_dir=Path.cwd())
```
Note that the name of the dependency in the function signature of component B has to match the name `comp_a` defined in the assembly.

## Components & Containers
My implementation takes advantage of built-in Python syntax to do this in a seamless way. A component, or subsystem within KOI (see {py:mod}`koi_net.components`), just needs to define a function signature for it's `__init__` method with the names of the dependencies it needs to be injected with:

```python
class MyComponent:
	def __init__(self, comp_a, comp_b):
		...
```

For nicer syntax, many components are set up as dataclasses, which autogenerates an `__init__` method from a class signature:

```python
@dataclass
class MyComponent:
	comp_a: ComponentA
	comp_b: ComponentB
```

Component classes are contained with an assembly, which performs a few roles. For the developer, it's a simple interface for defining all of the components within a system:

```python
from koi_net.base import BaseAssembly

class MyAssembly(BaseAssembly):
	comp_a = ComponentA
	comp_b = ComponentB
```

You'll notice the syntax is very similar to the component injection pattern, but instead we are assigning the component class or constructor to a component name. If that object is a `callable`, the assembly will inspect it's function signature to extract its requested dependencies, otherwise it will be treated as a constant. Occasionally you may want to treat a callable as a constant, in which case you can use the following decorator (the two available component types are `CompType.SINGLETON` and `CompType.OBJECT`):

```python
from koi_net.infra import provides, CompType

@provides(CompType.OBJECT)
class Component:
	...
```

When you initialize an assembler, it builds a dependency graph of all of the defined components and determines the initialization order by applying a topological sort (Kahn's algorithm). This ensures that a component's dependencies are always initialized before it is.

It's also important to note that when an assembler is initialized, it returns a container class with the instantiated versions of all of the components. This allows the container definition and instance to coexist with very lightweight syntax. Multiple containers can be instantiated from the same assembly, and will each have their own unique instances of components.

Using this system, changing the dependencies of a component only requires updating its class definition. It also becomes trivial to swap in replacement components by keeping the name, but changing the constructor assigned in the assembly's class definition.

```python
class AssemblyA:
	comp_a = CompA
	comp_b = CompB
	
class AssemblyB(AssemblyA):
	comp_a = CompA2
```

## Lifecycle Dependencies
In addition to initialization, there is a second layer of component ordering for lifecycle components, which define a start and/or stop method. When you run lifecycle methods on the assembly (start, stop, run), it will start up all components based on these secondary orderings.

If a component implements a `start` or `stop` method it will become part of the start or stop orderings respectively. The same dependency graph solver is used to compute this. In order to add start or stop dependencies, the `depends_on` decorator is used directly on the method:

```python
from koi_net.infra import depends_on

class LifeCycleComponent:
	@depends_on("comp_a")
	def start(self):
		...
	
	def stop(self):
		...
```

If a component defines both a start and stop method, but doesn't declare explicit dependencies for the stop method, it approximates stop dependencies by obtaining them from the reverse of the start graph.

Lifecycle methods are defined on the returned container, not the assembler. A lifecycle subsystem manages startup and shutdown of components based on the order defined in the build artifact. It does some error handling, bringing down the whole system if a component throws an exception on startup. This is important as many lifecycle components run within their own thread, and can cause unpredictable behavior if they can crash without affecting other threads.

The main thread is actually kept open, as the lifecycle subsystem starts as its own thread to manage threaded components. Within KOI, the "primary thread" would probably be the server (full nodes) or poller (partial nodes), as it handles I/O with other nodes and sends work to other threads.

## Inter-component Communication
There are several components which operate in their own threads. While the "primary thread" can be understood as either the server or poller, there isn't a real main thread, just that these subsystems handle input from the network which most behavior is downstream from.

The default threaded components are:
- `EventProcessingWorker`
- `KnowledgeProcessingWorker`
- `NodePoller` (partial nodes only)
- `NodeServer` (full nodes only)

Communication between these threads are facilitated by the following components:
- `KobjQueue`
- `EventQueue`
- `EventBuffer` (poll)
- `EventBuffer` (broadcast)

The knowledge object queue facilitates indirect communication between the server/poller and the knowledge processing worker. Producers put incoming knowledge objects into the queue, which are pulled out and pushed into the knowledge processing pipeline.

The event queue serves a similar role for outgoing events. Within the processing pipeline, knowledge objects may be sent to other nodes by pushing them into this queue. The even processing worker pulls them out, and then places them into the poll or broadcast event buffer, depending on whether the target node is partial or full respectively. When a node polls another node, it will receive the contents of the poll event buffer. The broadcast event buffer is used to batch high volumes of events that are queued within a short timeframe. When the buffer reaches a max size, or duration it is flushed and broadcasted to the target.
