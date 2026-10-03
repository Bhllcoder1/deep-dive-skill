#!/usr/bin/env python3
"""Validate .excalidraw files: JSON, required fields, unique ids, and every arrow
binding / text container / bound element pointing at an existing id.

    python3 docs/tools/check_excalidraw.py docs/*.excalidraw
"""

import json
import sys

REQUIRED = ("id", "type", "x", "y", "width", "height", "strokeColor", "backgroundColor", "seed", "version")


def check(path):
    errors = []
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    if doc.get("type") != "excalidraw" or doc.get("version") != 2:
        errors.append("top-level type/version must be 'excalidraw'/2")
    if not isinstance(doc.get("appState"), dict):
        errors.append("missing appState")
    elements = doc.get("elements")
    if not isinstance(elements, list) or not elements:
        return errors + ["elements must be a non-empty list"]

    ids = {}
    for index, el in enumerate(elements):
        for field in REQUIRED:
            if field not in el:
                errors.append(f"element #{index} ({el.get('id')}): missing '{field}'")
        if el.get("id") in ids:
            errors.append(f"duplicate id {el['id']}")
        ids[el.get("id")] = el

    arrows = texts = bound_refs = 0
    for el in elements:
        eid = el["id"]
        if el["type"] == "arrow":
            arrows += 1
            for side in ("startBinding", "endBinding"):
                binding = el.get(side)
                if not binding or binding.get("elementId") not in ids:
                    errors.append(f"arrow {eid}: {side} does not point to an existing id")
                elif ids[binding["elementId"]]["type"] in ("text", "arrow"):
                    errors.append(f"arrow {eid}: {side} must bind to a box, not {ids[binding['elementId']]['type']}")
        if el["type"] == "text" and el.get("containerId") is not None:
            texts += 1
            container = ids.get(el["containerId"])
            if container is None:
                errors.append(f"text {eid}: containerId {el['containerId']} not found")
            elif not any(b.get("id") == eid for b in (container.get("boundElements") or [])):
                errors.append(f"text {eid}: container {el['containerId']} does not list it in boundElements")
        for ref in el.get("boundElements") or []:
            bound_refs += 1
            target = ids.get(ref.get("id"))
            if target is None:
                errors.append(f"{eid}: boundElements references missing id {ref.get('id')}")
            elif ref.get("type") == "arrow" and target["type"] == "arrow":
                b = [target.get("startBinding"), target.get("endBinding")]
                if not any(x and x.get("elementId") == eid for x in b):
                    errors.append(f"{eid}: lists arrow {ref['id']} that is not bound back to it")
    print(f"{path}: {len(elements)} elements, {arrows} arrows, {texts} bound labels, "
          f"{bound_refs} bound refs -> {'OK' if not errors else str(len(errors)) + ' ERROR(S)'}")
    return errors


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    failed = False
    for path in argv:
        problems = check(path)
        for problem in problems:
            print("  ✗", problem)
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
