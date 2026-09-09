#!/usr/bin/env python3
"""Map each converted collection to the converter domain that writes it.

Collections and frame parameters are named "<prefix>_<BANK>_<Readable>", and
each is created by a put() or parameters() call under src/<Domain>/. The
directory name is the domain: Tracking, Calorimeter, Pid, Vertex, Truth, Btag,
Event.

Some put() sites pass the bank as a variable, assigned a literal elsewhere in
the same file. The bank is therefore matched against every string literal in
the file; the readable name is always the last literal in the call. A
collection re-emitted by a later pass belongs to the domain that writes it
first.

Names resolving to no domain, or to more than one, are reported to the caller
rather than given a default.
"""
import re
from pathlib import Path

# A put() statement: everything between "put(" and the closing ");".
_PUT = re.compile(r"\bput\s*\(([^;]*?)\)\s*;", re.S)
_PARAMETERS = re.compile(r'\bparameters\s*\(\s*"([^"\\]*)"')
_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')
# A pass-2 writer names a pass-1 collection to read it back.
_SDSTNAME = re.compile(r'\bsdstName\(\s*"[^"\\]*"\s*,\s*"([^"\\]*)"')
# A putParameter() call: an optional literal bank, then the key.
_PUTPARAM = re.compile(r'\bputParameter\(\s*(?:"[^"\\]*"|\w+)\s*,\s*"([^"\\]*)"')


def _readables(text):
    """Readable names this file puts.

    A name the file also reads back through sdstName() is being re-emitted, and
    belongs to the domain that puts it first.
    """
    passthrough = set(_SDSTNAME.findall(text))
    found = set()
    for args in _PUT.findall(text):
        literals = _LITERAL.findall(args)
        if literals and literals[-1] not in passthrough:
            found.add(literals[-1])
    return found


def index(src_root):
    """domain -> what its sources name.

    reads     readable names it puts
    literals  every string literal in its files, for matching the bank
    groups    banks passed to parameters()
    keys      keys passed to putParameter()
    """
    out = {}
    for path in sorted(Path(src_root).glob("*/*.cpp")):
        text = path.read_text()
        found = {
            "reads":  _readables(text),
            "groups": set(_PARAMETERS.findall(text)),
            "keys":   set(_PUTPARAM.findall(text)),
        }
        if not any(found.values()):
            continue
        found["literals"] = set(_LITERAL.findall(text))
        entry = out.setdefault(path.parent.name,
                               {k: set() for k in
                                ("reads", "literals", "groups", "keys")})
        for key, value in found.items():
            entry[key] |= value
    return out


def attribute(names, domain_index):
    """Map names to domains.

    Returns (domains, unattributed, ambiguous). Problems are returned rather
    than raised, so a run reports all of them at once.
    """
    domains, unattributed, ambiguous = {}, [], {}
    for name in sorted(names):
        parts = name.split("_", 2)          # prefix, bank, readable
        if len(parts) != 3:
            unattributed.append(name)
            continue
        _, bank, readable = parts
        hits = sorted(d for d, e in domain_index.items()
                      if readable in e["reads"] and bank in e["literals"])
        if not hits:
            # Frame parameters: the key names it, the bank says which writer.
            hits = sorted(d for d, e in domain_index.items()
                          if (readable in e["keys"] and bank in e["literals"])
                          or bank in e["groups"])
        if len(hits) == 1:
            domains[name] = hits[0]
        elif hits:
            ambiguous[name] = hits
        else:
            unattributed.append(name)
    return domains, unattributed, ambiguous
