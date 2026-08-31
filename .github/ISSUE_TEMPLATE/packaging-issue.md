---
name: Packaging or repository problem
about: A problem with the packages, their dependencies, an upgrade, or the repository itself
labels: []
---

<!--
This repository packages and distributes Asterisk; it does not develop it.
Bugs in Asterisk itself (dialplan behavior, protocol handling, features)
belong upstream: https://github.com/asterisk/asterisk/issues

A crash is worth reporting HERE first only so the packaging can be ruled
in or out (a module split apart from a companion it needs, a missing
dependency). If the packaging turns out fine, the report moves upstream.
-->

**What happened, and what did you expect?**


**Installed version and suite** (paste the output):

```
apt policy asterisk
```

**Installed module groups** (paste the output):

```
dpkg -l 'asterisk-modules-*' | grep '^ii'
```

**For crashes:** a backtrace with symbols. Install the matching dbgsym
packages from the `trixie-debug` suite first — see the instructions at
https://packages.zamfono.com/debian/asterisk

```
(backtrace here)
```
