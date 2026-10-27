"""Clone an authored scope into a weapon appearance exported by WolvenKit.

The caller performs CR2W conversion and archive packing with WolvenKit. This
script edits JSON only and validates the original appearance data semantically.
"""
import argparse
import copy
import json
from pathlib import Path

NAMES = ("vr_optic_low", "vr_optic_surface", "vr_optic_panel",
         "vr_optic_reticle_front", "vr_optic_reticle_front_panel",
         "vr_optic_reticle_rear", "vr_optic_reticle_rear_panel")


def walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def handles(doc):
    result = {}
    for item in walk(doc):
        if isinstance(item, dict) and "HandleId" in item:
            key = str(item["HandleId"])
            assert key not in result, f"Duplicate handle definition {key}"
            result[key] = item["Data"]
    for item in walk(doc):
        if isinstance(item, dict) and "HandleRefId" in item:
            assert str(item["HandleRefId"]) in result, f"Undefined handle {item}"
    return result


def semantic(value, definitions, active=frozenset()):
    if isinstance(value, dict):
        if "HandleRefId" in value or "HandleId" in value:
            key = str(value.get("HandleRefId", value.get("HandleId")))
            assert key not in active, f"Unexpected cyclic handle graph {key}"
            return semantic(definitions[key], definitions, active | {key})
        return {key: semantic(item, definitions, active) for key, item in value.items()
                if key != "BufferId"}
    if isinstance(value, list):
        return [semantic(item, definitions, active) for item in value]
    return value


def appearances(doc):
    return {item["Data"]["name"]["$value"]: item["Data"]
            for item in doc["Data"]["RootChunk"]["appearances"]}


def named(components, name):
    values = [item for item in components if item.get("name", {}).get("$value") == name]
    assert len(values) == 1, f"Expected one component named {name}, got {len(values)}"
    return values[0]


def clone_components(components, source_handles, target_doc):
    counter = max(int(key) for key in handles(target_doc)) + 1
    remap = {}

    def clone(value):
        nonlocal counter
        if isinstance(value, dict):
            if "HandleRefId" in value or "HandleId" in value:
                old = str(value.get("HandleRefId", value.get("HandleId")))
                if old in remap:
                    return {"HandleRefId": remap[old]}
                new = str(counter); counter += 1; remap[old] = new
                return {"HandleId": new, "Data": clone(source_handles[old])}
            return {key: clone(item) for key, item in value.items()}
        if isinstance(value, list):
            return [clone(item) for item in value]
        return copy.deepcopy(value)

    return [clone(item) for item in components]


def references_only(value):
    if isinstance(value, dict):
        if "HandleId" in value:
            return {"HandleRefId": value["HandleId"]}
        return {key: references_only(item) for key, item in value.items()}
    if isinstance(value, list):
        return [references_only(item) for item in value]
    return copy.deepcopy(value)


def validate(baseline, patched, donor, appearance, donor_appearance):
    bh, ph, dh = handles(baseline), handles(patched), handles(donor)
    before, after, source = appearances(baseline), appearances(patched), appearances(donor)
    assert before.keys() == after.keys(), "Appearance set changed"
    original_root = {key: item for key, item in baseline["Data"]["RootChunk"].items() if key != "appearances"}
    patched_root = {key: item for key, item in patched["Data"]["RootChunk"].items() if key != "appearances"}
    assert semantic(original_root, bh) == semantic(patched_root, ph), "Resource properties changed"
    for name, old in before.items():
        new = after[name]
        if name != appearance:
            assert semantic(old, bh) == semantic(new, ph), f"Untouched appearance changed: {name}"
            continue
        for key in old:
            if key not in ("components", "compiledData"):
                assert semantic(old[key], bh) == semantic(new[key], ph), f"Appearance property changed: {key}"
        for key in ("components",):
            count = len(old[key])
            assert len(new[key]) == count + len(NAMES)
            assert semantic(old[key], bh) == semantic(new[key][:count], ph), "Original components changed"
        old_package, new_package = old["compiledData"]["Data"], new["compiledData"]["Data"]
        count = len(old_package["Chunks"])
        assert len(new_package["Chunks"]) == count + len(NAMES)
        assert semantic(old_package["Chunks"], bh) == semantic(new_package["Chunks"][:count], ph), "Original cooked roots changed"
        for key, item in old_package.items():
            if key not in ("Chunks", "CruidDict"):
                assert item == new_package[key], f"Cooked package setting changed: {key}"
        expected = [named(source[donor_appearance]["compiledData"]["Data"]["Chunks"], n) for n in NAMES]
        actual = new_package["Chunks"][count:]
        assert semantic(expected, dh) == semantic(actual, ph), "Donor component or binding changed"
        assert semantic(new["components"][-len(NAMES):], ph) == semantic(actual, ph), "Component/cooked lists diverge"
        for key, item in old_package["CruidDict"].items():
            assert new_package["CruidDict"][key] == item, "Original CRUID mapping changed"
        ids = [item["id"] for item in new["components"]]
        added_ids = ids[-len(NAMES):]
        assert len(set(added_ids)) == len(added_ids) and not set(added_ids) & set(ids[:-len(NAMES)]), "Component CRUID collision"
        for offset, item in enumerate(actual, count):
            assert new_package["CruidDict"][str(offset)] == item["id"], "New CRUID mapping is wrong"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--donor", required=True, type=Path)
    parser.add_argument("--appearance", required=True)
    parser.add_argument("--donor-appearance", required=True)
    parser.add_argument("--scope-component", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-roundtrip", type=Path)
    args = parser.parse_args()
    baseline, donor = (json.loads(path.read_text(encoding="utf-8")) for path in (args.baseline, args.donor))
    if args.validate_roundtrip:
        patched = json.loads(args.validate_roundtrip.read_text(encoding="utf-8"))
        validate(baseline, patched, donor, args.appearance, args.donor_appearance)
        print("Roundtrip validated: all original properties/appearances/roots preserved; seven donor roots and bindings exact")
        return
    assert args.output, "--output is required when building"
    bh, dh = handles(baseline), handles(donor)
    target = appearances(baseline)[args.appearance]
    source = appearances(donor)[args.donor_appearance]
    # An integrated scope must have the same authored frame as its standalone donor.
    # Differences require a separate measured asset; no transform is guessed here.
    for name in ("Scope", args.scope_component):
        old, src = named(target["components"], name), named(source["components"], name)
        for key in ("localTransform", "visualScale", "parentTransform", "skinning", "rig", "graph"):
            assert semantic(old.get(key), bh) == semantic(src.get(key), dh), f"Scope frame differs: {name}.{key}"
    assert not any(item.get("name", {}).get("$value") in NAMES for item in target["components"]), "Already patched"
    patched = copy.deepcopy(baseline)
    result = appearances(patched)[args.appearance]
    roots = source["compiledData"]["Data"]["Chunks"]
    additions = clone_components([named(roots, n) for n in NAMES], dh, patched)
    package = result["compiledData"]["Data"]
    first = len(package["Chunks"])
    package["Chunks"].extend(additions)
    result["components"].extend(references_only(additions))
    for index, component in enumerate(additions, first):
        package["CruidDict"][str(index)] = component["id"]
    validate(baseline, patched, donor, args.appearance, args.donor_appearance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(patched, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(f"Patched {args.appearance}: {first} -> {first+len(NAMES)} components; authored frame matches donor")


if __name__ == "__main__":
    main()
