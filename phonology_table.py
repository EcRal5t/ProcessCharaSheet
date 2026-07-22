"""Compact entropy-based Middle-Chinese-to-modern correspondence tables."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from phonology import MC_INITIALS, MC_RHYMES, MCPosition, CorrespondenceModel


@dataclass(frozen=True)
class TableObservation:
    char: str
    outcome: str
    display_outcome: str
    position: MCPosition
    weight: float


@dataclass
class EntropyNode:
    observations: tuple[TableObservation, ...]
    split_feature: str | None = None
    children: dict[tuple[str, ...], "EntropyNode"] | None = None


@dataclass(frozen=True)
class TableRule:
    base: str
    conditions: tuple[tuple[str, str], ...]
    outcomes: tuple[str, ...]
    entropy_bits: float
    information_gain_bits: float
    char_count: int


FEATURE_LABELS = {
    "openness": "呼",
    "she": "攝",
    "division": "等",
    "chongniu": "重紐",
    "rhyme": "韻",
    "initial": "聲母",
    "group": "組",
    "voicing": "清濁",
    "tone": "調",
}

# Fixed description-length cost in bits.  Broad binary features are cheap;
# naming an exact rhyme/initial must buy substantially more entropy reduction.
FEATURE_COSTS = {
    "openness": 0.0,
    "division": 0.05,
    "chongniu": 0.05,
    "she": 0.20,
    "group": 0.05,
    "voicing": 0.05,
    "rhyme": 1.40,
    "initial": 0.60,
    "tone": 0.05,
}


def _normalise_checked_coda(final: str) -> str:
    """Map checked codas onto their homorganic nasal series for tree fitting."""
    if final.endswith("p"):
        return f"{final[:-1]}m"
    if final.endswith("t"):
        return f"{final[:-1]}n"
    if final.endswith("k"):
        return f"{final[:-1]}ng"
    return final


def _feature(position: MCPosition, name: str) -> str:
    values = {
        "openness": position.effective_openness,
        "she": position.she,
        "division": position.effective_division,
        "chongniu": position.chongniu,
        "rhyme": position.rhyme,
        "initial": position.initial,
        "group": position.group,
        "voicing": position.voicing,
        "tone": position.tone,
    }
    value = values[name] or "無"
    # In a binary 開/合 table, intrinsically neutral rhymes belong to the
    # non-labialised side; their rhyme/she condition can still split below it.
    return "開" if name == "openness" and value == "中" else value


def _weighted_counts(
    observations: Iterable[TableObservation],
    *,
    display: bool = False,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for observation in observations:
        outcome = observation.display_outcome if display else observation.outcome
        counts[outcome] += observation.weight
    return counts


def _entropy(observations: Sequence[TableObservation]) -> float:
    counts = _weighted_counts(observations)
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return -sum(
        (count / total) * math.log2(count / total)
        for count in counts.values()
        if count > 0
    )


def _weight(observations: Sequence[TableObservation]) -> float:
    return sum(observation.weight for observation in observations)


def _purity(observations: Sequence[TableObservation]) -> float:
    counts = _weighted_counts(observations)
    total = sum(counts.values())
    return max(counts.values(), default=0.0) / total if total else 0.0


def _modes(
    observations: Sequence[TableObservation],
    limit: int = 4,
    *,
    display: bool = False,
) -> tuple[str, ...]:
    counts = _weighted_counts(observations, display=display)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return ()
    floor = ranked[0][1] * 0.2
    modes = [outcome for outcome, count in ranked if count >= floor][:limit]
    if len(ranked) > len(modes) and len(modes) == limit:
        modes[-1] += "…"
    return tuple(modes)


def _partitions(
    observations: Sequence[TableObservation],
    feature: str,
    minimum_leaf_weight: float,
) -> dict[tuple[str, ...], tuple[TableObservation, ...]]:
    raw: defaultdict[str, list[TableObservation]] = defaultdict(list)
    for observation in observations:
        raw[_feature(observation.position, feature)].append(observation)
    large = {
        (value,): tuple(rows)
        for value, rows in raw.items()
        if _weight(rows) >= minimum_leaf_weight
        or (_weight(rows) >= 2.0 and _purity(rows) >= 0.75)
    }
    small_values = sorted(
        value for value, rows in raw.items()
        if not (
            _weight(rows) >= minimum_leaf_weight
            or (_weight(rows) >= 2.0 and _purity(rows) >= 0.75)
        )
    )
    if small_values:
        small_rows = tuple(
            row
            for value in small_values
            for row in raw[value]
        )
        if _weight(small_rows) >= minimum_leaf_weight:
            large[tuple(small_values)] = small_rows
        elif large:
            small_modes = _modes(small_rows)
            compatible = [
                key for key, rows in large.items()
                if _modes(rows) == small_modes
            ]
            target = compatible[0] if compatible else max(large, key=lambda key: _weight(large[key]))
            rows = large.pop(target)
            large[tuple(sorted((*target, *small_values)))] = (*rows, *small_rows)
    # Fold values that already predict the same meaningful outcome modes before
    # charging the split complexity.  This strongly favours compact conditions.
    folded: defaultdict[tuple[str, ...], list[tuple[tuple[str, ...], tuple[TableObservation, ...]]]] = defaultdict(list)
    for values, rows in large.items():
        folded[_modes(rows)].append((values, rows))
    return {
        tuple(sorted(value for values, _rows in group for value in values)): tuple(
            row for _values, rows in group for row in rows
        )
        for group in folded.values()
    }


def _build_tree(
    observations: Sequence[TableObservation],
    features: Sequence[str],
    *,
    depth: int,
    max_depth: int,
    minimum_leaf_weight: float,
    minimum_gain_bits: float,
    minimum_relative_gain: float,
    complexity_strength: float,
) -> EntropyNode:
    node = EntropyNode(tuple(observations))
    parent_entropy = _entropy(observations)
    total_weight = _weight(observations)
    if depth >= max_depth or parent_entropy < 0.08 or total_weight < minimum_leaf_weight * 2:
        return node

    best: tuple[float, float, str, dict[tuple[str, ...], tuple[TableObservation, ...]]] | None = None
    for feature in features:
        partitions = _partitions(observations, feature, minimum_leaf_weight)
        if len(partitions) < 2:
            continue
        covered = sum(_weight(rows) for rows in partitions.values())
        if covered < total_weight * 0.9:
            continue
        conditional_entropy = sum(
            _weight(rows) / covered * _entropy(rows)
            for rows in partitions.values()
        )
        gain = parent_entropy - conditional_entropy
        penalty = (
            complexity_strength
            * (len(partitions) - 1)
            * math.log2(total_weight + 1)
            / total_weight
        )
        penalized = gain - penalty - FEATURE_COSTS[feature] / (depth + 1)
        candidate = (penalized, gain, feature, partitions)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return node
    penalized, gain, feature, partitions = best
    if (
        penalized <= 0
        or gain < minimum_gain_bits
        or gain / max(parent_entropy, 1e-12) < minimum_relative_gain
    ):
        return node

    remaining = tuple(value for value in features if value != feature)
    children = {
        values: _build_tree(
            rows,
            remaining,
            depth=depth + 1,
            max_depth=max_depth,
            minimum_leaf_weight=minimum_leaf_weight,
            minimum_gain_bits=minimum_gain_bits,
            minimum_relative_gain=minimum_relative_gain,
            complexity_strength=complexity_strength,
        )
        for values, rows in partitions.items()
    }

    # Merge sibling leaves with the same meaningful modern outcomes.  This is
    # the entropy-tree equivalent of folding irrelevant phonological positions.
    merged: dict[tuple[str, ...], EntropyNode] = {}
    leaf_groups: defaultdict[tuple[str, ...], list[tuple[tuple[str, ...], EntropyNode]]] = defaultdict(list)
    for values, child in children.items():
        if child.split_feature is None:
            leaf_groups[_modes(child.observations)].append((values, child))
        else:
            merged[values] = child
    for group in leaf_groups.values():
        values = tuple(sorted(value for branch, _child in group for value in branch))
        rows = tuple(row for _branch, child in group for row in child.observations)
        merged[values] = EntropyNode(rows)
    if len(merged) < 2:
        return node
    node.split_feature = feature
    node.children = merged
    return node


def _branch_label(values: tuple[str, ...]) -> str:
    if len(values) <= 3:
        return "/".join(values)
    return f"其餘{len(values)}類"


def _rules_from_tree(
    base: str,
    node: EntropyNode,
    component: str,
    conditions: tuple[tuple[str, str], ...] = (),
    base_entropy: float | None = None,
) -> list[TableRule]:
    if base_entropy is None:
        base_entropy = _entropy(node.observations)
    if node.split_feature is None or not node.children:
        entropy = _entropy(node.observations)
        # The final tree is fitted on nasalised coda classes, but that mapping
        # is only an analytical device: keep both members of a regular
        # -m/-p, -n/-t or -ng/-k series visible in the final table.  Tone can
        # only have created separate branches when a difference survived the
        # normalisation.
        display_original = component == "final"
        return [TableRule(
            base,
            conditions,
            _modes(node.observations, display=display_original),
            entropy,
            max(base_entropy - entropy, 0.0),
            len({observation.char for observation in node.observations}),
        )]
    rules = []
    label = FEATURE_LABELS[node.split_feature]
    for values, child in sorted(node.children.items(), key=lambda item: item[0]):
        rules.extend(_rules_from_tree(
            base,
            child,
            component,
            (*conditions, (label, _branch_label(values))),
            base_entropy,
        ))
    return rules


def build_correspondence_rules(
    model: CorrespondenceModel,
    component: str,
    *,
    minimum_leaf_weight: float = 6.0,
    minimum_gain_bits: float = 0.15,
    minimum_relative_gain: float = 0.12,
    complexity_strength: float = 0.8,
    max_depth: int = 3,
) -> tuple[TableRule, ...]:
    if component == "initial":
        base_function: Callable[[MCPosition], str] = lambda position: position.initial
        outcome_function = lambda observation: observation.pair.pronunciation.initial
        feature_order = ("tone", "openness", "she", "division", "chongniu", "rhyme")
        base_order = MC_INITIALS
    elif component == "final":
        base_function = lambda position: position.rhyme
        outcome_function = lambda observation: observation.pair.pronunciation.final
        feature_order = ("tone", "group", "voicing", "initial", "openness", "division", "chongniu")
        base_order = MC_RHYMES
    else:
        raise ValueError(f"unsupported correspondence-table component: {component}")

    grouped: defaultdict[str, list[TableObservation]] = defaultdict(list)
    for observation in model.component_observations[component]:
        pair = observation.pair
        display_outcome = outcome_function(observation)
        outcome = (
            _normalise_checked_coda(display_outcome)
            if component == "final"
            else display_outcome
        )
        grouped[base_function(pair.position)].append(TableObservation(
            pair.char,
            outcome,
            display_outcome,
            pair.position,
            observation.weight,
        ))
    rules = []
    for base in base_order:
        observations = grouped.get(base)
        if not observations:
            continue
        tree = _build_tree(
            observations,
            feature_order,
            depth=0,
            max_depth=max_depth,
            minimum_leaf_weight=minimum_leaf_weight,
            minimum_gain_bits=minimum_gain_bits,
            minimum_relative_gain=minimum_relative_gain,
            complexity_strength=complexity_strength,
        )
        rules.extend(_rules_from_tree(base, tree, component))
    return tuple(rules)


def render_correspondence_tables(model: CorrespondenceModel) -> str:
    lines = [
        "[聲母歸併]",
        "中古聲母\t附加地位\t現聲母\t條件熵(bits)\t降熵(bits)\t字數",
    ]
    for rule in build_correspondence_rules(model, "initial"):
        conditions = ",".join(f"{name}={value}" for name, value in rule.conditions) or "—"
        lines.append(
            f"{rule.base}\t{conditions}\t{'/'.join(rule.outcomes)}\t"
            f"{rule.entropy_bits:.2f}\t{rule.information_gain_bits:.2f}\t{rule.char_count}"
        )
    lines.extend((
        "[韻母歸併]",
        "中古韻\t附加地位\t現韻母\t條件熵(bits)\t降熵(bits)\t字數",
    ))
    for rule in build_correspondence_rules(model, "final"):
        conditions = ",".join(f"{name}={value}" for name, value in rule.conditions) or "—"
        lines.append(
            f"{rule.base}\t{conditions}\t{'/'.join(rule.outcomes)}\t"
            f"{rule.entropy_bits:.2f}\t{rule.information_gain_bits:.2f}\t{rule.char_count}"
        )
    return "\n".join(lines)
